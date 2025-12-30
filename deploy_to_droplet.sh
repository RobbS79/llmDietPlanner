#!/bin/bash
# Script to deploy to DigitalOcean Droplet
# Usage: ./deploy_to_droplet.sh user@droplet_ip

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 user@droplet_ip"
    echo "Example: $0 django@123.456.789.0"
    exit 1
fi

DROPLET=$1
REMOTE_DIR="~/llmDietPlanner"

echo "🚀 Deploying to DigitalOcean Droplet: $DROPLET"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create a .env file with your production settings."
    exit 1
fi

# Copy .env file (make sure it's not in .gitignore)
echo "📋 Copying environment file..."
scp .env $DROPLET:$REMOTE_DIR/.env

# SSH into droplet and pull latest code
echo "📥 Pulling latest code from repository..."
ssh $DROPLET "cd $REMOTE_DIR && git checkout prod && git pull origin prod"

# Build and restart services
echo "🔨 Building and starting services..."
ssh $DROPLET "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml up -d --build"

# Run migrations
echo "🗄️  Running database migrations..."
ssh $DROPLET "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput"

# Collect static files (if needed, though Dockerfile.prod already does this)
echo "📦 Collecting static files..."
ssh $DROPLET "cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput"

echo "✅ Deployment complete!"
echo ""
echo "To view logs: ssh $DROPLET 'cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml logs -f'"
echo "To restart: ssh $DROPLET 'cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml restart'"

