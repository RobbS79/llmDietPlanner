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

from diet_planner.models import DietaryGoal
from diet_planner.tasks import process_dietary_goal_task
from .models import ShopifyStore, ShopifyCheckout

logger = logging.getLogger(__name__)


def verify_shopify_webhook(request: HttpRequest, store: ShopifyStore) -> bool:
    """
    Verify that the webhook request is authentic from Shopify.
    Uses HMAC-SHA256 signature verification.

    Shopify sends the signature in the X-Shopify-Hmac-Sha256 header.
    """
    shopify_hmac = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not shopify_hmac:
        logger.warning("Shopify webhook missing HMAC header")
        return False

    # Get the webhook secret from the store
    # Note: The webhook secret is different from the API keys
    # You need to set this up in Shopify Admin > Settings > Notifications > Webhooks
    webhook_secret = store.get_webhook_secret()
    if not webhook_secret:
        logger.error(f"Store {store.name} has no webhook secret configured")
        return False

    # Calculate expected HMAC
    body = request.body
    computed_hmac = base64.b64encode(
        hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).digest()
    ).decode('utf-8')

    # Compare in constant time to prevent timing attacks
    return hmac.compare_digest(computed_hmac, shopify_hmac)


@csrf_exempt
@require_POST
def shopify_order_paid_webhook(request: HttpRequest) -> HttpResponse:
    """
    Webhook endpoint called by Shopify when an order is paid.

    Expected flow:
    1. User clicks "Generate Plan" → creates DietaryGoal with status='awaiting_payment'
    2. User redirected to Shopify checkout → pays
    3. Shopify sends webhook here with order details
    4. We find the DietaryGoal via order metadata (goal_id)
    5. Update goal status to 'payment_confirmed'
    6. Trigger Celery task for meal plan generation

    Webhook URL: /api/shopify/webhooks/order-paid/
    Configure in Shopify Admin: Settings > Notifications > Webhooks
    """
    try:
        # Parse the webhook body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Shopify webhook: Invalid JSON body")
            return HttpResponse("Invalid JSON", status=400)

        # Get shop domain from header
        shop_domain = request.headers.get('X-Shopify-Shop-Domain', '')
        logger.info(f"Received order-paid webhook from shop: {shop_domain}")

        # Find the store
        store = ShopifyStore.objects.filter(
            store_domain__icontains=shop_domain.replace('.myshopify.com', ''),
            is_active=True
        ).first()

        if not store:
            logger.warning(f"No active store found for domain: {shop_domain}")
            # Return 200 to prevent Shopify from retrying
            # (could be a misconfigured webhook)
            return HttpResponse("Store not found", status=200)

        # Verify HMAC signature (skip in development if secret not set)
        # In production, this MUST be enforced
        if store.get_webhook_secret():
            if not verify_shopify_webhook(request, store):
                logger.error(f"Shopify webhook HMAC verification failed for store: {store.name}")
                return HttpResponse("Unauthorized", status=401)
        else:
            logger.warning(f"Webhook secret not configured for store: {store.name} - skipping verification")

        # Extract order details
        order_id = data.get('id')
        order_name = data.get('name', f"Order #{order_id}")
        financial_status = data.get('financial_status', '')

        logger.info(f"Processing order: {order_name} (ID: {order_id}, Status: {financial_status})")

        # Only process paid orders
        if financial_status not in ('paid', 'partially_paid'):
            logger.info(f"Order {order_name} not paid yet (status: {financial_status}) - skipping")
            return HttpResponse("OK - Not paid yet", status=200)

        # Look for goal_id in custom attributes or note_attributes
        goal_id = None

        # Check note_attributes first (set during checkout creation)
        note_attributes = data.get('note_attributes', [])
        for attr in note_attributes:
            if attr.get('name') == 'goal_id':
                try:
                    goal_id = int(attr.get('value'))
                except (ValueError, TypeError):
                    pass
                break

        # Also check custom_attributes if present
        if not goal_id:
            custom_attributes = data.get('custom_attributes', [])
            for attr in custom_attributes:
                if attr.get('name') == 'goal_id':
                    try:
                        goal_id = int(attr.get('value'))
                    except (ValueError, TypeError):
                        pass
                    break

        # Check line items for metadata
        if not goal_id:
            line_items = data.get('line_items', [])
            for item in line_items:
                properties = item.get('properties', [])
                for prop in properties:
                    if prop.get('name') == 'goal_id':
                        try:
                            goal_id = int(prop.get('value'))
                        except (ValueError, TypeError):
                            pass
                        break
                if goal_id:
                    break

        if not goal_id:
            logger.warning(f"Order {order_name} has no goal_id in metadata - may be a manual order")
            return HttpResponse("OK - No goal_id", status=200)

        # Find the DietaryGoal
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
        except DietaryGoal.DoesNotExist:
            logger.error(f"DietaryGoal {goal_id} not found for order {order_name}")
            return HttpResponse("Goal not found", status=200)

        # Check if already processed (idempotency)
        if goal.status not in ('awaiting_payment', 'pending'):
            logger.info(f"Goal {goal_id} already processed (status: {goal.status}) - skipping")
            return HttpResponse("OK - Already processed", status=200)

        # Update goal status
        goal.status = DietaryGoal.StatusChoices.PAYMENT_CONFIRMED
        goal.payment_confirmed_at = timezone.now()
        goal.save(update_fields=['status', 'payment_confirmed_at', 'updated_at'])

        logger.info(f"Updated goal {goal_id} to payment_confirmed")

        # Update checkout status if we have it
        if goal.shopify_checkout_id:
            ShopifyCheckout.objects.filter(
                checkout_id=goal.shopify_checkout_id
            ).update(
                status='completed',
                order_id=str(order_id),
                updated_at=timezone.now()
            )

        # Trigger Celery task for meal plan generation (v2 with multi-phase architecture)
        try:
            task = process_dietary_goal_task.delay(goal.id)
            goal.celery_task_id = task.id
            goal.save(update_fields=['celery_task_id', 'updated_at'])
            logger.info(f"Triggered meal plan generation task {task.id} for goal {goal_id}")
        except Exception as e:
            logger.error(f"Failed to trigger Celery task for goal {goal_id}: {e}")
            # Mark as failed so user knows something went wrong
            goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
            goal.error_message = "Failed to start meal plan generation. Please contact support."
            goal.save(update_fields=['status', 'error_message', 'updated_at'])
            return HttpResponse("Task trigger failed", status=500)

        return HttpResponse("OK", status=200)

    except Exception as e:
        logger.exception(f"Shopify webhook error: {e}")
        # Return 500 so Shopify will retry
        return HttpResponse(f"Internal error: {str(e)}", status=500)


@csrf_exempt
@require_POST
def shopify_order_cancelled_webhook(request: HttpRequest) -> HttpResponse:
    """
    Webhook for order cancellation events.
    Updates DietaryGoal status if order is cancelled.
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('id')

        logger.info(f"Received order-cancelled webhook for order {order_id}")

        # Find goal by checking checkouts with this order_id
        checkout = ShopifyCheckout.objects.filter(order_id=str(order_id)).first()
        if checkout and checkout.metadata:
            goal_id = checkout.metadata.get('goal_id')
            if goal_id:
                try:
                    goal = DietaryGoal.objects.get(id=goal_id)
                    if goal.status == DietaryGoal.StatusChoices.AWAITING_PAYMENT:
                        goal.status = DietaryGoal.StatusChoices.FAILED
                        goal.error_message = "Order was cancelled."
                        goal.save(update_fields=['status', 'error_message', 'updated_at'])
                        logger.info(f"Updated goal {goal_id} to failed due to cancelled order")
                except DietaryGoal.DoesNotExist:
                    pass

        return HttpResponse("OK", status=200)
    except Exception as e:
        logger.exception(f"Shopify order-cancelled webhook error: {e}")
        return HttpResponse("OK", status=200)
