"""
Shopify webhook handlers for order and payment events.
"""
import hashlib
import hmac
import json
import base64
import logging
from django.http import HttpResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import transaction

from diet_planner.models import DietaryGoal
from diet_planner.tasks import process_dietary_goal_task
from .models import ShopifyStore, ShopifyCheckout

logger = logging.getLogger(__name__)


def verify_shopify_webhook(request: HttpRequest, store: ShopifyStore) -> bool:
    """
    Verify that the webhook request is authentic from Shopify.
    Uses HMAC-SHA256 signature verification.
    """
    shopify_hmac = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not shopify_hmac:
        logger.warning("Shopify webhook missing HMAC header")
        return False

    webhook_secret = store.get_webhook_secret()
    if not webhook_secret:
        logger.error(f"Store {store.name} has no webhook secret configured")
        return False

    body = request.body
    computed_hmac = base64.b64encode(
        hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).digest()
    ).decode('utf-8')

    return hmac.compare_digest(computed_hmac, shopify_hmac)


def _extract_goal_id(data: dict) -> int | None:
    """Extract goal_id from Shopify order data (note_attributes, custom_attributes, line items)."""
    for source in ('note_attributes', 'custom_attributes'):
        for attr in data.get(source, []):
            if attr.get('name') == 'goal_id':
                try:
                    return int(attr.get('value'))
                except (ValueError, TypeError):
                    pass

    for item in data.get('line_items', []):
        for prop in item.get('properties', []):
            if prop.get('name') == 'goal_id':
                try:
                    return int(prop.get('value'))
                except (ValueError, TypeError):
                    pass
    return None


@csrf_exempt
@require_POST
def shopify_order_paid_webhook(request: HttpRequest) -> HttpResponse:
    """
    Webhook called by Shopify when an order is paid.
    Uses select_for_update + atomic transaction for idempotency.
    """
    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Shopify webhook: Invalid JSON body")
            return HttpResponse("Invalid JSON", status=400)

        shop_domain = request.headers.get('X-Shopify-Shop-Domain', '')
        logger.info(f"Received order-paid webhook from shop: {shop_domain}")

        store = ShopifyStore.objects.filter(
            store_domain__icontains=shop_domain.replace('.myshopify.com', ''),
            is_active=True
        ).first()

        if not store:
            logger.warning(f"No active store found for domain: {shop_domain}")
            return HttpResponse("Store not found", status=404)

        # HMAC verification is mandatory
        if not verify_shopify_webhook(request, store):
            logger.error(f"Shopify webhook HMAC verification failed for store: {store.name}")
            return HttpResponse("Unauthorized", status=401)

        order_id = data.get('id')
        order_name = data.get('name', f"Order #{order_id}")
        financial_status = data.get('financial_status', '')

        logger.info(f"Processing order: {order_name} (ID: {order_id}, Status: {financial_status})")

        if financial_status not in ('paid', 'partially_paid'):
            logger.info(f"Order {order_name} not paid (status: {financial_status})")
            return HttpResponse("OK", status=200)

        goal_id = _extract_goal_id(data)
        if not goal_id:
            logger.warning(f"Order {order_name} has no goal_id in metadata")
            return HttpResponse("OK", status=200)

        # Atomic transaction with row lock for idempotency
        with transaction.atomic():
            try:
                goal = DietaryGoal.objects.select_for_update().get(id=goal_id)
            except DietaryGoal.DoesNotExist:
                logger.error(f"DietaryGoal {goal_id} not found for order {order_name}")
                return HttpResponse("Goal not found", status=500)

            if goal.status not in ('awaiting_payment', 'pending', 'payment_pending'):
                logger.info(f"Goal {goal_id} already processed (status: {goal.status})")
                return HttpResponse("OK", status=200)

            goal.shopify_order_id = str(order_id)
            goal.status = DietaryGoal.StatusChoices.PAYMENT_PENDING
            goal.payment_confirmed_at = timezone.now()
            goal.save(update_fields=['status', 'payment_confirmed_at', 'shopify_order_id', 'updated_at'])

            if goal.shopify_checkout_id:
                ShopifyCheckout.objects.filter(
                    checkout_id=goal.shopify_checkout_id
                ).update(
                    status='completed',
                    order_id=str(order_id),
                    updated_at=timezone.now()
                )

        # Trigger Celery task outside the transaction (so the commit is visible to the worker)
        try:
            task = process_dietary_goal_task.delay(goal.id)
            goal.celery_task_id = task.id
            goal.save(update_fields=['celery_task_id', 'updated_at'])
            logger.info(f"Triggered meal plan generation task {task.id} for goal {goal_id}")
        except Exception as e:
            logger.error(f"Failed to trigger Celery task for goal {goal_id}: {e}")
            goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
            goal.error_message = "Failed to start meal plan generation. Please contact support."
            goal.save(update_fields=['status', 'error_message', 'updated_at'])
            return HttpResponse("Task trigger failed", status=500)

        return HttpResponse("OK", status=200)

    except Exception as e:
        logger.exception("Shopify order-paid webhook error")
        return HttpResponse("Internal error", status=500)


@csrf_exempt
@require_POST
def shopify_order_cancelled_webhook(request: HttpRequest) -> HttpResponse:
    """
    Webhook for order cancellation events.
    """
    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Shopify cancel webhook: Invalid JSON body")
            return HttpResponse("Invalid JSON", status=400)

        shop_domain = request.headers.get('X-Shopify-Shop-Domain', '')
        store = ShopifyStore.objects.filter(
            store_domain__icontains=shop_domain.replace('.myshopify.com', ''),
            is_active=True
        ).first()

        if not store:
            logger.warning(f"No active store found for domain: {shop_domain}")
            return HttpResponse("Store not found", status=404)

        # HMAC verification is mandatory
        if not verify_shopify_webhook(request, store):
            logger.error(f"Shopify cancel webhook HMAC verification failed for store: {store.name}")
            return HttpResponse("Unauthorized", status=401)

        order_id = data.get('id')

        logger.info(f"Received order-cancelled webhook for order {order_id}")

        checkout = ShopifyCheckout.objects.filter(order_id=str(order_id)).first()
        if checkout and checkout.metadata:
            goal_id = checkout.metadata.get('goal_id')
            if goal_id:
                with transaction.atomic():
                    try:
                        goal = DietaryGoal.objects.select_for_update().get(id=goal_id)
                        if goal.status in ('awaiting_payment', 'pending', 'payment_pending'):
                            goal.status = DietaryGoal.StatusChoices.FAILED
                            goal.error_message = "Order was cancelled."
                            goal.save(update_fields=['status', 'error_message', 'updated_at'])
                            logger.info(f"Updated goal {goal_id} to failed due to cancelled order")
                    except DietaryGoal.DoesNotExist:
                        pass

        return HttpResponse("OK", status=200)
    except Exception as e:
        logger.exception("Shopify order-cancelled webhook error")
        return HttpResponse("Internal error", status=500)
