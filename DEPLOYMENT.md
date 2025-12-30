# Deployment Guide for DigitalOcean

This guide covers deploying the LLM Diet Planner Django application to DigitalOcean App Platform.

## Prerequisites

1. A DigitalOcean account
2. Your code pushed to a GitHub repository
3. Docker installed locally (for testing)

## Deployment Options

### Option 1: DigitalOcean App Platform (Recommended for MVP)

DigitalOcean App Platform is the easiest way to deploy. It handles:
- Automatic deployments from GitHub
- Database provisioning
- SSL certificates
- Scaling

#### Steps:

1. **Push your code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin YOUR_GITHUB_REPO_URL
   git push -u origin main
   ```

2. **Create App in DigitalOcean Dashboard**
   - Go to https://cloud.digitalocean.com/apps
   - Click "Create App"
   - Connect your GitHub account
   - Select your repository and branch

3. **Configure the App**
   - DigitalOcean will detect the Dockerfile
   - Update the `.do/app.yaml` file with your actual values:
     - Replace `YOUR_GITHUB_USERNAME/llmDietPlanner` with your actual repo
     - Update `ALLOWED_HOSTS` with your app's domain

4. **Add Environment Variables**
   In the App Platform dashboard, add these environment variables:
   - `SECRET_KEY`: Generate a new secret key (use `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
   - `DEBUG`: Set to `False` for production
   - `DATABASE_URL`: Will be automatically set if you add a database
   - `ALLOWED_HOSTS`: Your app domain (e.g., `your-app.ondigitalocean.app`)

5. **Add a Database**
   - In the App Platform, click "Add Resource" → "Database"
   - Choose PostgreSQL
   - The `DATABASE_URL` will be automatically injected

6. **Deploy**
   - Click "Deploy"
   - DigitalOcean will build and deploy your app

### Option 2: DigitalOcean Droplet with Docker

For more control, you can deploy to a Droplet:

1. **Create a Droplet**
   - Choose Ubuntu 22.04
   - Install Docker and Docker Compose

2. **Push to Docker Hub or DigitalOcean Container Registry**
   ```bash
   # Build production image
   docker build -f Dockerfile.prod -t your-username/llm-diet-planner:latest .
   
   # Tag for DigitalOcean Container Registry
   docker tag your-username/llm-diet-planner:latest registry.digitalocean.com/your-registry/llm-diet-planner:latest
   
   # Push to registry
   docker push registry.digitalocean.com/your-registry/llm-diet-planner:latest
   ```

3. **Deploy on Droplet**
   - SSH into your Droplet
   - Pull and run the container
   - Set up environment variables
   - Use docker-compose or run directly

## Environment Variables

Set these in DigitalOcean App Platform or your deployment environment:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | Generated secret |
| `DEBUG` | Debug mode | `False` for production |
| `DATABASE_URL` | Database connection string | Auto-set by App Platform |
| `ALLOWED_HOSTS` | Allowed hostnames | `your-app.ondigitalocean.app` |

## Database Migrations

Migrations run automatically on deployment if you use the production Dockerfile. To run manually:

```bash
# In App Platform, use the console or add a pre-deploy command
python manage.py migrate
```

## Static Files

Static files are collected during the Docker build process using WhiteNoise middleware. They're served directly by Django/Gunicorn.

## Post-Deployment

1. **Create a superuser**
   - Use the App Platform console
   - Run: `python manage.py createsuperuser`

2. **Verify deployment**
   - Visit your app URL
   - Check admin panel at `/admin/`

## Troubleshooting

- **Check logs**: Use `doctl apps logs <app-id>` or view in the dashboard
- **Database connection**: Ensure `DATABASE_URL` is set correctly
- **Static files**: Verify `STATIC_ROOT` is set and collectstatic runs
- **Allowed hosts**: Make sure your domain is in `ALLOWED_HOSTS`

## Cost Estimate

- App Platform Basic ($5-12/month for small apps)
- PostgreSQL Database ($15/month for production, $7 for dev)
- Total: ~$20-27/month for a small production app

