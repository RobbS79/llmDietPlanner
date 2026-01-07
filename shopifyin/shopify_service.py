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
        Create a Shopify checkout.
        
        Args:
            line_items: List of line items, each with 'variantId' and 'quantity'
                       Example: [{"variantId": "gid://shopify/ProductVariant/123", "quantity": 1}]
            email: Optional customer email
            shipping_address: Optional shipping address dict
            note: Optional note for the order
            custom_attributes: Optional custom attributes
            
        Returns:
            Checkout data including checkout ID, token, and web URL
        """
        # Build custom attributes
        attributes_list = []
        if custom_attributes:
            for attr in custom_attributes:
                attributes_list.append({
                    "key": attr.get("key", ""),
                    "value": attr.get("value", ""),
                })

        # Build shipping address input
        shipping_address_input = None
        if shipping_address:
            shipping_address_input = {
                "address1": shipping_address.get("address1", ""),
                "address2": shipping_address.get("address2"),
                "city": shipping_address.get("city", ""),
                "country": shipping_address.get("country", ""),
                "province": shipping_address.get("province"),
                "zip": shipping_address.get("zip", ""),
                "firstName": shipping_address.get("firstName"),
                "lastName": shipping_address.get("lastName"),
            }

        query = """
        mutation checkoutCreate($input: CheckoutCreateInput!) {
            checkoutCreate(input: $input) {
                checkout {
                    id
                    webUrl
                    token
                    totalPrice {
                        amount
                        currencyCode
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
                checkoutUserErrors {
                    field
                    message
                }
            }
        }
        """

        variables = {
            "input": {
                "lineItems": line_items,
            }
        }

        if email:
            variables["input"]["email"] = email
        if shipping_address_input:
            variables["input"]["shippingAddress"] = shipping_address_input
        if note:
            variables["input"]["note"] = note
        if attributes_list:
            variables["input"]["customAttributes"] = attributes_list

        data = self._execute_graphql_query(query, variables)
        checkout_create = data.get("checkoutCreate", {})

        # Check for user errors
        errors = checkout_create.get("checkoutUserErrors", [])
        if errors:
            error_messages = [err.get("message", "Unknown error") for err in errors]
            raise Exception(f"Checkout creation errors: {', '.join(error_messages)}")

        checkout = checkout_create.get("checkout")
        if not checkout:
            raise Exception("No checkout returned from Shopify API")

        return checkout

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

