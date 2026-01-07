# Shopify UI Setup Guide - Step by Step

This guide walks you through exactly what to do in the Shopify Admin UI to set up the API integration.

## Prerequisites
- You have access to your Shopify store admin (the store shown in your screenshot: `mealprep-9693`)
- You're logged in as the store owner or have admin permissions

---

## Step 1: Navigate to Apps & Sales Channels

1. **Look at the left sidebar** in your Shopify admin (you should see this when logged in)

2. **Scroll down to the bottom** - you'll see a **gear icon (⚙️) with "Settings"**

3. **Click on "Settings"**

4. In the Settings menu, **click on "Apps and sales channels"**

   > This page shows all apps installed in your store

---

## Step 2: Access Developer Apps

1. On the "Apps and sales channels" page, **look at the top right corner**

2. You should see a button/link that says **"Develop apps"** or **"Manage private apps"**

   > If you don't see this, you might need to enable it:
   - Look for a link like "Allow custom app development" or "Enable private app development"
   - Some stores have this in: Settings → Plans and permissions → Additional settings

3. **Click "Develop apps"** (or "Create a custom app" if you see that instead)

---

## Step 3: Create Your Custom App

1. **Click the button "Create an app"** (usually at the top right)

2. **A popup or form will appear** asking for:
   - **App name**: Enter something like `Django API Integration` or `Diet Planner Backend`
   - (You can leave other fields as default)

3. **Click "Create app"**

---

## Step 4: Configure Storefront API Permissions

After creating the app, you'll see tabs at the top. Look for:

1. **Click on the "Configuration" tab** (or "API access" tab)

2. **Scroll down** until you find a section called **"Storefront API"** or **"Storefront API access scopes"**

3. **Expand this section** (click on it if it's collapsed)

4. **Look for a checkbox** that says:
   - ✅ `unauthenticated_write_checkouts`
   
   **Check this box** - this is the minimum required permission

5. **Optional but recommended** - also check:
   - ✅ `unauthenticated_read_product_listings` (if you want to list products)
   - ✅ `unauthenticated_read_product_inventory` (if you want to check availability)

6. **Scroll up and click "Save"** button (usually at the top right)

---

## Step 5: Install the App

1. **Look at the top right** of the page - there should be a button that says **"Install app"**

2. **Click "Install app"**

3. A confirmation dialog might appear - **click "Install"** to confirm

   > This activates the app and generates the API token

---

## Step 6: Get Your Access Token

1. After installation, **click on the "API credentials" tab** (or look for "Credentials" section)

2. **Scroll down** to find **"Storefront API access token"** section


4. **Click the "Reveal token once"** button (or "Copy" button) next to it

5. **IMPORTANT**: 
   - **Copy this token immediately** - paste it somewhere safe (text file, password manager)
   - You won't be able to see it again (only regenerate)
   - This is what you'll paste into Django Admin

6. The token format looks like: 
   ```

   shpat_YOUR_TOKEN_HERE

   ```

---

## Step 7: Note Your Store Domain

1. **Look at your browser's address bar** - you should see something like:
   ```
   admin.shopify.com/store/mealprep-9693
   ```

2. Your **store domain** is: `mealprep-9693.myshopify.com`
   - Take the part after `/store/` (in this case: `mealprep-9693`)
   - Add `.myshopify.com` to the end

---

## Step 8: Add to Django Admin

Now you have everything you need:

1. **Store Domain**: `mealprep-9693.myshopify.com` (your store's domain)
2. **Storefront Access Token**: `shpat_xxxxx...` (the token you copied)

**In Django Admin:**

1. Go to your Django admin panel
2. Navigate to **Shopify → Shopify Stores**
3. Click **"Add Shopify Store"**
4. Fill in:
   - **Name**: `MealPrep` (or any name you like)
   - **Store Domain**: `mealprep-9693.myshopify.com`
   - **Storefront Access Token**: Paste the token you copied
   - **Is Active**: ✅ Check this box
5. Click **"Save"**

---

## Troubleshooting

### "I don't see 'Develop apps' button"
- Make sure you're logged in as the store owner
- Check Settings → Plans and permissions → look for app development settings
- Some stores need to enable "Private app development" first

### "I can't find Storefront API section"
- Make sure you're on the **Configuration** or **API access** tab
- It might be under "API credentials" tab instead
- Look for "Storefront API" or "Storefront API access scopes"

### "The token is hidden"
- Click "Reveal token once" - it only shows once for security
- If you missed it, you can regenerate it:
  - Go back to API credentials
  - Look for "Regenerate token" button
  - Generate a new one (old token will stop working)

### "What if I see 'Admin API' instead?"
- You need **Storefront API**, not Admin API
- Admin API is for different purposes (managing orders, products from backend)
- Storefront API is specifically for creating checkouts

---

## Quick Checklist

- [ ] Created custom app in Shopify
- [ ] Enabled `unauthenticated_write_checkouts` scope
- [ ] Installed the app
- [ ] Copied Storefront API access token
- [ ] Noted store domain (format: `yourstore.myshopify.com`)
- [ ] Added store configuration in Django Admin
- [ ] Tested creating a checkout via API

---

## Next Steps

Once configured, test the integration:

1. Make sure you have at least one product in your Shopify store
2. Get the product variant ID (you'll need this for checkout creation)
3. Test the API endpoint: `POST /api/shopify/checkouts/`

For getting product variant IDs, you can:
- Use Shopify Admin → Products → Click product → Look at URL or product details
- Or use GraphQL query in Shopify's GraphQL explorer (advanced)


