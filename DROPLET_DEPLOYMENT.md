# DigitalOcean Droplet Deployment Guide

This guide covers deploying the LLM Diet Planner Django application to a DigitalOcean Droplet.

## Prerequisites

1. A DigitalOcean account
2. A domain name (optional, but recommended)
3. Basic knowledge of SSH and Linux commands

## Step 1: Create a Droplet

1. Go to https://cloud.digitalocean.com/droplets/new
2. Choose:
   - **Image**: Ubuntu 22.04 (LTS)
   - **Plan**: Basic ($6/month minimum for 1GB RAM, or $12/month for 2GB recommended)
   - **Datacenter region**: Choose closest to your users
   - **Authentication**: SSH keys (recommended) or root password
3. Click "Create Droplet"
4. Note the IP address of your droplet

## Step 2: Initial Server Setup

### Connect to your Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

### Create a non-root user (recommended)

```bash
# Create user
adduser django
usermod -aG sudo django

# Copy SSH keys to new user
rsync --archive --chown=django:django ~/.ssh /home/django

# Switch to new user
su - django
```

### Update system packages

```bash
sudo apt update && sudo apt upgrade -y
```

## Step 3: Install Docker and Docker Compose

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Log out and back in for group changes to take effect
exit
# SSH back in
```

## Step 4: Clone Your Repository

```bash
# Install git if not already installed
sudo apt install git -y

# Clone your repository
git clone https://github.com/RobbS79/llmDietPlanner.git
cd llmDietPlanner

# Switch to prod branch
git checkout prod
```

## Step 5: Configure Environment Variables

Create a `.env` file:

```bash
cd llmDietPlanner
nano .env
```

Add the following (replace with your values):

```env
SECRET_KEY=your-generated-secret-key-here
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,YOUR_DROPLET_IP
POSTGRES_PASSWORD=your-strong-database-password-here
```

Generate a secret key:

```bash
# On your local machine, generate a key
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Copy the output and paste it in .env as SECRET_KEY
```

Save and exit (Ctrl+X, then Y, then Enter).

## Step 6: Build and Start Services

### Option A: Without Nginx (Simple, for testing)

```bash
# Build and start services
docker compose -f docker-compose.yml up -d --build

# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Collect static files
docker compose exec web python manage.py collectstatic --noinput
```

Your app will be available at `http://YOUR_DROPLET_IP:8000`

### Option B: With Nginx (Production-ready)

First, set up Nginx configuration:

```bash
# Create nginx directory
mkdir -p nginx/ssl

# Create nginx config (see nginx/nginx.conf.example)
# Then build and start
docker compose -f docker-compose.prod.yml up -d --build

# Run migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Create superuser
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# Collect static files (already done in Dockerfile.prod)
```

## Step 7: Set Up Nginx (Optional but Recommended)

### Create Nginx Configuration

```bash
mkdir -p nginx
nano nginx/nginx.conf
```

Use the example configuration provided in `nginx/nginx.conf.example`.

### Set Up SSL with Let's Encrypt (Recommended)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## Step 8: Set Up Firewall

```bash
# Allow SSH
sudo ufw allow OpenSSH

# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow port 8000 (if not using Nginx)
sudo ufw allow 8000/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

## Step 9: Set Up Auto-start on Reboot

Create a systemd service (optional):

```bash
sudo nano /etc/systemd/system/llm-diet-planner.service
```

Add:

```ini
[Unit]
Description=LLM Diet Planner Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/django/llmDietPlanner
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable the service:

```bash
sudo systemctl enable llm-diet-planner.service
sudo systemctl start llm-diet-planner.service
```

## Useful Commands

### View logs
```bash
docker compose -f docker-compose.prod.yml logs -f
```

### Stop services
```bash
docker compose -f docker-compose.prod.yml down
```

### Restart services
```bash
docker compose -f docker-compose.prod.yml restart
```

### Access Django shell
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell
```

### Run migrations
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

### Create superuser
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

### Update code
```bash
cd ~/llmDietPlanner
git pull origin prod
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

## Database Backup

### Manual backup
```bash
docker compose -f docker-compose.prod.yml exec db pg_dump -U llm_diet_planner llm_diet_planner > backup_$(date +%Y%m%d).sql
```

### Restore backup
```bash
docker compose -f docker-compose.prod.yml exec -T db psql -U llm_diet_planner llm_diet_planner < backup_20231230.sql
```

## Security Checklist

- [ ] Change default SSH port (optional)
- [ ] Disable root login via SSH
- [ ] Set up SSH keys instead of passwords
- [ ] Configure firewall (UFW)
- [ ] Set up SSL/HTTPS
- [ ] Use strong database password
- [ ] Keep system updated: `sudo apt update && sudo apt upgrade`
- [ ] Set `DEBUG=False` in production
- [ ] Configure `ALLOWED_HOSTS` properly
- [ ] Set up regular backups

## Troubleshooting

### Check if containers are running
```bash
docker compose -f docker-compose.prod.yml ps
```

### Check container logs
```bash
docker compose -f docker-compose.prod.yml logs web
docker compose -f docker-compose.prod.yml logs db
```

### Access container shell
```bash
docker compose -f docker-compose.prod.yml exec web sh
```

### Check disk space
```bash
df -h
docker system df
```

### Clean up Docker (if low on space)
```bash
docker system prune -a
```

## Cost Estimate

- **Droplet**: $6-12/month (1-2GB RAM)
- **Domain**: ~$10-15/year (optional)
- **Total**: ~$6-12/month

Compare to App Platform: ~$20-27/month (but includes managed database and automatic deployments)

