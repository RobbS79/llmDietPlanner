# Quick Start - Droplet Deployment

## Fastest Path to Deploy

### 1. Create Droplet
- Go to https://cloud.digitalocean.com/droplets/new
- Choose Ubuntu 22.04, Basic plan ($6-12/month)
- Create droplet and note the IP

### 2. Initial Server Setup

**Option A: Use the setup script (Recommended)**
```bash
# Copy setup script to droplet
scp setup_droplet.sh root@YOUR_DROPLET_IP:/tmp/

# SSH into droplet
ssh root@YOUR_DROPLET_IP

# Run setup script
bash /tmp/setup_droplet.sh
```

**Option B: Manual setup**
```bash
# SSH into droplet
ssh root@YOUR_DROPLET_IP

# Run these commands:
apt update && apt upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
apt install -y docker-compose-plugin git
adduser django
usermod -aG sudo,docker django
```

### 3. Configure Environment

```bash
# Switch to django user
su - django

# Clone repository
git clone https://github.com/RobbS79/llmDietPlanner.git
cd llmDietPlanner
git checkout prod

# Create .env file
nano .env
```

Add to `.env`:
```env
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=YOUR_DROPLET_IP,your-domain.com
POSTGRES_PASSWORD=strong-password-here
```

Generate secret key (on your local machine):
```bash
python3 generate_secret_key.py
```

### 4. Deploy

**Simple deployment (no Nginx):**
```bash
docker compose -f docker-compose.yml up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Access at: `http://YOUR_DROPLET_IP:8000`

**Production deployment (with Nginx):**
```bash
# Create nginx config from example
cp nginx/nginx.conf.example nginx/nginx.conf
# Edit nginx.conf and replace your-domain.com with your actual domain

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

### 5. Set Up SSL (Optional but Recommended)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## Updating Your App

**Method 1: Use deployment script (from your local machine)**
```bash
./deploy_to_droplet.sh django@YOUR_DROPLET_IP
```

**Method 2: Manual update (SSH into droplet)**
```bash
ssh django@YOUR_DROPLET_IP
cd ~/llmDietPlanner
git pull origin prod
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

## Common Commands

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f

# Stop services
docker compose -f docker-compose.prod.yml down

# Restart services
docker compose -f docker-compose.prod.yml restart

# Access Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Check container status
docker compose -f docker-compose.prod.yml ps
```

## Cost Comparison

| Option | Monthly Cost | Notes |
|--------|--------------|-------|
| **Droplet** | $6-12 | More control, manual management |
| **App Platform** | $20-27 | Easier, managed, auto-deployments |

Choose Droplet if you want more control and lower cost.
Choose App Platform if you want easier deployment and management.

