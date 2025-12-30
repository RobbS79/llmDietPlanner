# DigitalOcean App Platform - Step by Step Setup

## Where to Add Environment Variables (Including SECRET_KEY)

After you've connected your GitHub repository and DigitalOcean detects your Dockerfile, you'll see the app configuration screen. Here's where to add your secret key:

### Step-by-Step:

1. **After connecting GitHub and selecting your repository**, you'll see the "Components" or "Resources" section

2. **Look for "Environment Variables" or "App-Level Environment Variables"**
   - This is usually in the configuration panel on the right side
   - Or in a tab/section called "Environment" or "Config"

3. **Click "Add Variable" or the "+" button**

4. **Add the SECRET_KEY variable:**
   - **Key**: `SECRET_KEY`
   - **Value**: Paste your generated secret key here
   - **Scope**: Usually "Run Time" (RUN_TIME)
   - **Type**: "Plain Text" (unless you want to mark it as "SECRET" for extra security, which hides it in the UI)

5. **Add other required variables:**
   - `DEBUG` = `False`
   - `ALLOWED_HOSTS` = Your app domain (you'll get this after creation, like `your-app-name.ondigitalocean.app`)

6. **For DATABASE_URL:**
   - This is automatically set when you add a PostgreSQL database component
   - You don't need to manually set this - just add the database component and it's handled automatically

### Visual Guide:

The interface typically looks like this:

```
┌─────────────────────────────────┐
│ Environment Variables           │
├─────────────────────────────────┤
│ Key          Value      Scope   │
│ ──────────────────────────────  │
│ SECRET_KEY   [paste]    RUN_TIME│ ← Add here
│ DEBUG        False      RUN_TIME│
│ ALLOWED_...  your-app... RUN...│
└─────────────────────────────────┘
      [+ Add Variable]
```

### Important Notes:

- **Generate the key first** (before adding it):
  ```bash
  python generate_secret_key.py
  ```
  
- **Copy the entire output** - it's a long string of characters

- **Paste it exactly** - no spaces, no quotes needed

- **You can mark it as "SECRET" type** in DigitalOcean - this hides the value in the UI for security (recommended)

- **If you miss this step**, you can add environment variables later by:
  - Going to your app in App Platform
  - Settings → App-Level Environment Variables
  - Add the variable there

### Example SECRET_KEY value:

It will look something like this (much longer in reality):
```
django-insecure-abc123def456ghi789jkl012mno345pqr678stu901vwx234yz
```

But your generated one will be different and much longer.

