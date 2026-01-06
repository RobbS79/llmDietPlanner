# Shopify Partners Dashboard Setup Guide

Since you're using the Shopify Partners/Developer dashboard, here's what to fill for a backend-only integration:

## Understanding Your Setup

You're creating an **app** in the Partners dashboard. For a simple Django backend integration that just creates checkouts, you have two options:

### Option 1: Simple Custom App (Recommended for MVP)
- Go directly to your **store admin** (not Partners dashboard)
- Create a **private app** (see SHOPIFY_SETUP_GUIDE.md)
- This is simpler and faster

### Option 2: Use Partners Dashboard (What you're doing now)
- More complex but allows the app to be used in multiple stores
- Requires app URL and configuration

---

## How to Fill the Partners Dashboard Form

### 1. App Name
✅ **Already filled**: `MealPrepOnetyOne` (you can change this if needed)

### 2. App URL
**What to put:**
```
https://your-django-backend-domain.com/shopify/app
```

**BUT WAIT** - For a **backend-only integration** (no embedded UI), you might not need this!

**Options:**
- **Option A**: Use a placeholder if you don't have a public URL yet
  ```
  https://yourdomain.com
  ```
- **Option B**: If your Django app is deployed, use your actual domain
  ```
  https://your-django-app.ondigitalocean.app/shopify
  ```

**For Storefront API only (creating checkouts), this URL isn't actually used by Shopify** - it's mainly for embedded apps or webhooks.

### 3. Embed app in Shopify admin
❌ **UNCHECK this** - You're not embedding a UI in Shopify admin, you're just using the API from Django.

### 4. Preferences URL (optional)
**Leave empty** - Not needed for API-only integration.

### 5. Webhooks API Version
✅ **Keep as `2026-01`** - This is fine for modern API version.

### 6. Access Section (IMPORTANT!)
**This is where you configure API permissions.**

**What to do:**
1. **Click on the "Access" section** (the empty text area)
2. **Look for "Storefront API"** or expand it
3. **Find and check:**
   - ✅ `unauthenticated_write_checkouts` - **This is required**
   - ✅ `unauthenticated_read_product_listings` - Optional but useful
   - ✅ `unauthenticated_read_product_inventory` - Optional

**Note:** You might also see "Admin API" scopes. You don't need those for checkout creation.

---

## Alternative: Skip Partners Dashboard (Simpler Approach)

If you just want to integrate with **your own store** (not create a public app), this is overcomplicated:

### Simpler Method - Direct Store Setup:

1. **Close this Partners dashboard**
2. **Go to your actual Shopify store admin**: `admin.shopify.com/store/mealprep-9693`
3. **Follow the steps in `SHOPIFY_SETUP_GUIDE.md`** instead

This creates a "private app" just for your store, which is much simpler and doesn't require:
- App URLs
- App embedding
- Partners dashboard configuration

---

## If You Continue with Partners Dashboard

### After Saving This Version:

1. **You'll need to install the app in your store**
2. **Get the Storefront API token:**
   - After installation, go to your store admin
   - Settings → Apps → Find your app
   - Get the Storefront API access token from there

### Why Partners Dashboard?
- ✅ Good if you want to create a public app used by multiple stores
- ✅ Good if you plan to publish to Shopify App Store later
- ❌ Overcomplicated for single-store backend integration

---

## My Recommendation

**For your MVP (Django backend creating checkouts):**

**Use the simpler method:**
1. Go to `admin.shopify.com/store/mealprep-9693`
2. Settings → Apps and sales channels → Develop apps → Create app
3. Configure Storefront API there
4. Much simpler, same functionality

**The Partners dashboard approach** is better if:
- You're building an app for multiple stores
- You plan to publish to Shopify App Store
- You need app store listing, reviews, etc.

---

## Quick Decision Guide

**Question:** "Do I need to sell this app to other stores?"

- **NO** → Use simple private app (store admin method)
- **YES** → Continue with Partners dashboard

Since you're building a diet planner for your own use, the **private app method is recommended**.

