"""
Shopify API Service.
Handles interactions with Shopify Storefront API for checkout creation.
"""
import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ShopifyService:
    """
    Service for interacting with Shopify Storefront API.
    Used for creating checkouts and managing orders.
    """
    
    def __init__(self, store_domain: str, storefront_token: str):
        """
        Initialize Shopify service.
        
        Args:
            store_domain: Shopify store domain (e.g., 'mealprep-9693.myshopify.com')
            storefront_token: Storefront API access token
        """
        self.store_domain = store_domain
        self.storefront_token = storefront_token
        self.api_url = f"https://{store_domain}/api/2025-01/graphql.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Storefront-Access-Token": storefront_token,
        }

    def _execute_graphql_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against Shopify Storefront API.
        
        Args:
            query: GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            Response data from Shopify API
            
        Raises:
            Exception: If API request fails
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
                raise Exception(f"Shopify API errors: {', '.join(error_messages)}")

            return data.get("data", {})

        except requests.exceptions.RequestException as e:
            logger.error(f"Shopify API request failed: {str(e)}")
            raise Exception(f"Failed to communicate with Shopify: {str(e)}")

    def create_checkout(
        self,
        line_items: List[Dict[str, Any]],
        email: Optional[str] = None,
        shipping_address: Optional[Dict[str, Any]] = None,
        note: Optional[str] = None,
        custom_attributes: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Create a Shopify cart (replaces deprecated checkout API).

        Args:
            line_items: List of line items, each with 'variantId' and 'quantity'
                       Example: [{"variantId": "gid://shopify/ProductVariant/123", "quantity": 1}]
            email: Optional customer email
            shipping_address: Optional shipping address dict (not used in cart API)
            note: Optional note for the order
            custom_attributes: Optional custom attributes

        Returns:
            Cart data including cart ID, token, and checkout URL
        """
        # Build cart lines from line items
        cart_lines = []
        for item in line_items:
            line = {
                "merchandiseId": item.get("variantId"),
                "quantity": item.get("quantity", 1),
            }
            # Add custom attributes to line item if provided
            if custom_attributes:
                line["attributes"] = [
                    {"key": attr.get("key", ""), "value": attr.get("value", "")}
                    for attr in custom_attributes
                ]
            cart_lines.append(line)

        # Build buyer identity if email provided
        buyer_identity = None
        if email:
            buyer_identity = {"email": email}

        query = """
        mutation cartCreate($input: CartInput!) {
            cartCreate(input: $input) {
                cart {
                    id
                    checkoutUrl
                    totalQuantity
                    cost {
                        totalAmount {
                            amount
                            currencyCode
                        }
                    }
                    lines(first: 100) {
                        edges {
                            node {
                                id
                                quantity
                                merchandise {
                                    ... on ProductVariant {
                                        id
                                        title
                                        price {
                                            amount
                                            currencyCode
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """

        variables = {
            "input": {
                "lines": cart_lines,
            }
        }

        if buyer_identity:
            variables["input"]["buyerIdentity"] = buyer_identity
        if note:
            variables["input"]["note"] = note

        data = self._execute_graphql_query(query, variables)
        cart_create = data.get("cartCreate", {})

        # Check for user errors
        errors = cart_create.get("userErrors", [])
        if errors:
            error_messages = [err.get("message", "Unknown error") for err in errors]
            raise Exception(f"Cart creation errors: {', '.join(error_messages)}")

        cart = cart_create.get("cart")
        if not cart:
            raise Exception("No cart returned from Shopify API")

        # Map cart response to checkout-like structure for compatibility
        return {
            "id": cart.get("id"),
            "webUrl": cart.get("checkoutUrl"),
            "token": cart.get("id", "").split("/")[-1] if cart.get("id") else "",
            "totalPrice": cart.get("cost", {}).get("totalAmount", {}),
        }

    def get_checkout(self, checkout_token: str) -> Dict[str, Any]:
        """
        Retrieve checkout details by token.
        
        Args:
            checkout_token: Shopify checkout token
            
        Returns:
            Checkout data
        """
        query = """
        query getCheckout($checkoutToken: ID!) {
            node(id: $checkoutToken) {
                ... on Checkout {
                    id
                    webUrl
                    token
                    email
                    totalPrice {
                        amount
                        currencyCode
                    }
                    completedAt
                    order {
                        id
                        name
                    }
                    lineItems(first: 100) {
                        edges {
                            node {
                                id
                                title
                                quantity
                                variant {
                                    id
                                    title
                                    price {
                                        amount
                                        currencyCode
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {"checkoutToken": checkout_token}
        data = self._execute_graphql_query(query, variables)
        node = data.get("node")

        if not node:
            raise Exception("Checkout not found")

        return node

    def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Get product details by Shopify product ID.
        
        Args:
            product_id: Shopify product ID (GraphQL GID)
            
        Returns:
            Product data or None if not found
        """
        query = """
        query getProduct($id: ID!) {
            product(id: $id) {
                id
                title
                description
                handle
                availableForSale
                variants(first: 10) {
                    edges {
                        node {
                            id
                            title
                            price {
                                amount
                                currencyCode
                            }
                            availableForSale
                            image {
                                url
                                altText
                            }
                        }
                    }
                }
                images(first: 5) {
                    edges {
                        node {
                            url
                            altText
                        }
                    }
                }
            }
        }
        """

        variables = {"id": product_id}
        
        try:
            data = self._execute_graphql_query(query, variables)
            return data.get("product")
        except Exception as e:
            logger.error(f"Failed to get product {product_id}: {str(e)}")
            return None

    def search_products(self, query: str = "", first: int = 10) -> List[Dict[str, Any]]:
        """
        Search for products in the store.
        
        Args:
            query: Search query string
            first: Number of results to return
            
        Returns:
            List of product data
        """
        graphql_query = """
        query searchProducts($query: String!, $first: Int!) {
            products(first: $first, query: $query) {
                edges {
                    node {
                        id
                        title
                        handle
                        availableForSale
                        variants(first: 1) {
                            edges {
                                node {
                                    id
                                    title
                                    price {
                                        amount
                                        currencyCode
                                    }
                                    availableForSale
                                    image {
                                        url
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {
            "query": query,
            "first": first,
        }

        try:
            data = self._execute_graphql_query(graphql_query, variables)
            products = data.get("products", {}).get("edges", [])
            return [edge["node"] for edge in products]
        except Exception as e:
            logger.error(f"Failed to search products: {str(e)}")
            return []

