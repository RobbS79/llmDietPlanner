#!/bin/bash
# Initial server setup script for DigitalOcean Droplet
# Run this on a fresh Ubuntu 22.04 droplet
# Usage: Run as root or with sudo

set -e

echo "🔧 Setting up DigitalOcean Droplet for Django deployment..."

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install essential packages
echo "📥 Installing essential packages..."
apt install -y curl git vim ufw

# Install Docker
echo "🐳 Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Install Docker Compose plugin
echo "🐙 Installing Docker Compose..."
apt install -y docker-compose-plugin

# Create django user (if it doesn't exist)
if ! id "django" &>/dev/null; then
    echo "👤 Creating django user..."
    adduser --disabled-password --gecos "" django
    usermod -aG sudo django
    usermod -aG docker django
fi

# Set up firewall
echo "🔥 Configuring firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Clone repository (if not already cloned)
if [ ! -d "/home/django/llmDietPlanner" ]; then
    echo "📥 Cloning repository..."
    su - django -c "git clone https://github.com/RobbS79/llmDietPlanner.git"
    su - django -c "cd llmDietPlanner && git checkout prod"
fi

echo "✅ Server setup complete!"
echo ""
echo "Next steps:"
echo "1. SSH as django user: su - django"
echo "2. Create .env file: cd llmDietPlanner && nano .env"
echo "3. Build and start: docker compose -f docker-compose.prod.yml up -d --build"
echo "4. Run migrations: docker compose -f docker-compose.prod.yml exec web python manage.py migrate"
echo "5. Create superuser: docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser"

