# Quick Start - DigitalOcean Deployment

## Quick Deployment Steps

1. **Generate a Secret Key**
   ```bash
   python generate_secret_key.py
   ```
   Copy the output for use in DigitalOcean.

2. **Push to GitHub**
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push
   ```

3. **Deploy to DigitalOcean App Platform**
   - Go to https://cloud.digitalocean.com/apps
   - Click "Create App"
   - Connect GitHub and select your repository
   - DigitalOcean will auto-detect the Dockerfile
   - Add a PostgreSQL database
   - Set environment variables:
     - `SECRET_KEY`: Paste the key from step 1
     - `DEBUG`: `False`
     - `ALLOWED_HOSTS`: Your app domain (will be shown after creation)
   - Click "Deploy"

4. **After Deployment**
   - Create superuser: Use the console in App Platform
   - Access admin at: `https://your-app.ondigitalocean.app/admin/`

## Environment Variables Needed

- `SECRET_KEY`: Django secret key (generate with `python generate_secret_key.py`)
- `DEBUG`: Set to `False` for production
- `DATABASE_URL`: Automatically set by App Platform when you add a database
- `ALLOWED_HOSTS`: Your app domain (e.g., `your-app.ondigitalocean.app`)

## Files Created

- `Dockerfile.prod`: Production Docker image
- `.do/app.yaml`: DigitalOcean App Platform configuration (optional, can configure via UI)
- `DEPLOYMENT.md`: Detailed deployment guide
- `generate_secret_key.py`: Script to generate Django secret key

