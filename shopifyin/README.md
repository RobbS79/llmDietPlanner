# Shopify Integration App

This Django app provides Shopify integration for creating checkouts and processing purchases.

## Features

- **Checkout Creation**: Create Shopify checkouts via API
- **Order Tracking**: Track checkout status and completed orders
- **Product Caching**: Cache product information for quick access
- **Secure Storage**: Encrypted API credentials following GDPR best practices

## Setup

### 1. Configure Shopify Store in Django Admin

1. Go to Django Admin → Shopify Stores
2. Click "Add Shopify Store"
3. Fill in:
   - **Name**: Display name (e.g., "MealPrep Store")
   - **Store Domain**: Your Shopify store domain (e.g., `mealprep-9693.myshopify.com`)
   - **Storefront Access Token**: Your Shopify Storefront API access token
   - **Is Active**: Check to enable

### 2. Get Shopify Storefront API Access Token

**Step-by-step guide:**

1. **Log into Shopify Admin** (admin.shopify.com/store/your-store-name)

2. **Navigate to Apps:**
   - Go to **Settings** (gear icon at bottom left)
   - Click **Apps and sales channels**
   - Click **Develop apps** (top right)

3. **Create a new app:**
   - Click **Create an app**
   - Enter app name (e.g., "Django Integration" or "Diet Planner API")
   - Click **Create app**

4. **Configure Storefront API:**
   - In your new app, click **Configure Admin API scopes** (or find **Storefront API** section)
   - Scroll down to **Storefront API** section
   - Under **Storefront API access scopes**, enable:
     - ✅ `unauthenticated_write_checkouts` (required - allows creating checkouts)
     - ✅ `unauthenticated_read_product_listings` (optional - for product listing)
     - ✅ `unauthenticated_read_product_inventory` (optional - for inventory checks)
   - Click **Save**

5. **Install the app:**
   - Click **Install app** button (top right)
   - Confirm installation

6. **Get the access token:**
   - After installation, go to **API credentials** tab
   - Under **Storefront API access token**, click **Reveal token once**
   - **Copy this token** - you'll need it for Django Admin
   - ⚠️ **Important**: Store this token securely. You won't be able to see it again (only regenerate)

7. **Note your store domain:**
   - Your store domain is visible in the URL: `admin.shopify.com/store/mealprep-9693`
   - The domain format is: `mealprep-9693.myshopify.com` (add `.myshopify.com`)

**What you need for Django:**
- Store Domain: `mealprep-9693.myshopify.com` (or your store name)
- Storefront Access Token: The token you copied in step 6

## API Endpoints

All endpoints require authentication (JWT token).

### Create Checkout

**POST** `/api/shopify/checkouts/`

Creates a new Shopify checkout and returns a checkout URL for redirect.

**Request:**
```json
{
  "store_id": 1,  // Optional, uses default active store
  "variant_ids": ["gid://shopify/ProductVariant/123"],
  "quantities": [1],
  "email": "user@example.com",  // Optional, uses user email if not provided
  "metadata": {
    "goal_id": 1,
    "custom_field": "value"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "checkout_id": 1,
    "checkout_url": "https://checkout.shopify.com/...",
    "checkout_token": "...",
    "total_price": "29.99",
    "currency": "USD"
  },
  "error": null
}
```

**Frontend Usage:**
```javascript
// When user clicks "Buy Now" button
const response = await fetch('/api/shopify/checkouts/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    variant_ids: ['gid://shopify/ProductVariant/123'],
    quantities: [1],
    metadata: { goal_id: currentGoalId }
  })
});

const { data } = await response.json();
// Redirect user to checkout
window.location.href = data.checkout_url;
```

### Get Checkout Status

**GET** `/api/shopify/checkouts/<checkout_id>/`

Retrieves the current status of a checkout. Automatically syncs with Shopify if completed.

**Response:**
```json
{
  "status": "success",
  "data": {
    "id": 1,
    "checkout_url": "https://checkout.shopify.com/...",
    "status": "completed",
    "total_price": "29.99",
    "currency": "USD",
    "order_id": "gid://shopify/Order/456",
    "order_number": "#1001",
    "completed_at": "2024-01-15T10:30:00Z"
  },
  "error": null
}
```

### List Checkouts

**GET** `/api/shopify/checkouts/list/`

Lists all checkouts for the authenticated user.

**Query Parameters:**
- `status`: Filter by status (optional: `created`, `pending`, `completed`, `expired`, `cancelled`)
- `limit`: Number of results (default: 50)
- `offset`: Offset for pagination (default: 0)

### List Products

**GET** `/api/shopify/products/`

Lists cached Shopify products.

**Query Parameters:**
- `store_id`: Filter by store (optional)
- `available_only`: Only show available products (default: `true`)

## Models

### ShopifyStore

Stores Shopify store configuration with encrypted credentials.

### ShopifyCheckout

Tracks checkout sessions, links users to Shopify orders.

**Status Values:**
- `created`: Checkout created but not accessed
- `pending`: Payment pending
- `completed`: Order completed
- `expired`: Checkout expired
- `cancelled`: Checkout cancelled

### ShopifyProduct

Cache of Shopify products for quick access (optional, can be populated via management commands or webhooks).

## Database Migration

After setting up, run migrations:

```bash
python manage.py makemigrations shopifyin
python manage.py migrate
```

## Security Notes

- All API tokens are stored encrypted using `encrypted_model_fields`
- Ensure `FIELD_ENCRYPTION_KEY` is set in your environment variables
- Storefront API tokens should have minimal required scopes
- Admin API credentials are optional and only needed for advanced order management

## Example Integration Flow

1. User clicks "Buy Now" button in your app
2. Frontend calls `POST /api/shopify/checkouts/` with product variant IDs
3. Backend creates checkout in Shopify and returns checkout URL
4. Frontend redirects user to checkout URL
5. User completes payment on Shopify
6. Optionally: Set up Shopify webhook to notify your app when order is completed
7. Check order status via `GET /api/shopify/checkouts/<id>/`

## Next Steps

- Set up Shopify webhooks for real-time order updates
- Create Celery task to sync product data periodically
- Add order management features using Admin API (if needed)

