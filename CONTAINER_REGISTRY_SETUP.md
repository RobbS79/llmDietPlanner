# Container Registry Setup Guide

If you've selected "Container Registry" as your source in DigitalOcean, you need to build and push your Docker image first. Here's how:

## Option 1: Use DigitalOcean Container Registry (Recommended if using Container Registry)

### Step 1: Create a Container Registry in DigitalOcean
1. Go to Container Registry in DigitalOcean dashboard
2. Create a new registry (if you don't have one)
3. Note your registry URL (e.g., `registry.digitalocean.com/your-registry-name`)

### Step 2: Install doctl (DigitalOcean CLI)
```bash
# macOS
brew install doctl

# Or download from: https://docs.digitalocean.com/reference/doctl/how-to/install/
```

### Step 3: Authenticate with DigitalOcean
```bash
doctl auth init
```

### Step 4: Login to Container Registry
```bash
doctl registry login
```

### Step 5: Build and Push Your Image
```bash
# From your project directory
cd /Users/robertsoroka/cursor_projects/llmDietPlanner/llmDietPlanner

# Build the production image
docker build -f Dockerfile.prod -t registry.digitalocean.com/YOUR_REGISTRY_NAME/llm-diet-planner:latest .

# Push to registry
docker push registry.digitalocean.com/YOUR_REGISTRY_NAME/llm-diet-planner:latest
```

### Step 6: Configure in DigitalOcean App Platform
- **Registry provider**: DigitalOcean Container Registry
- **Repository**: `YOUR_REGISTRY_NAME/llm-diet-planner`
- **Image tag or digest**: `latest`
- **Credentials**: Not needed (you're logged in via doctl)

---

## Option 2: Use Docker Hub

### Step 1: Create Docker Hub Account
1. Sign up at https://hub.docker.com (if you don't have an account)
2. Create a repository (e.g., `your-username/llm-diet-planner`)

### Step 2: Login to Docker Hub
```bash
docker login
# Enter your Docker Hub username and password
```

### Step 3: Build and Push Image
```bash
# From your project directory
cd /Users/robertsoroka/cursor_projects/llmDietPlanner/llmDietPlanner

# Build the production image
docker build -f Dockerfile.prod -t YOUR_DOCKERHUB_USERNAME/llm-diet-planner:latest .

# Push to Docker Hub
docker push YOUR_DOCKERHUB_USERNAME/llm-diet-planner:latest
```

### Step 4: Configure in DigitalOcean App Platform
- **Registry provider**: Docker Hub
- **Repository**: `YOUR_DOCKERHUB_USERNAME/llm-diet-planner`
- **Image tag or digest**: `latest`
- **Credentials**: `YOUR_DOCKERHUB_USERNAME:YOUR_ACCESS_TOKEN`
  - To get an access token: Docker Hub → Account Settings → Security → New Access Token

---

## Option 3: Use GitHub Container Registry

### Step 1: Enable GitHub Container Registry
Your repository must exist on GitHub first.

### Step 2: Build and Push to GitHub
```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# Build and tag
docker build -f Dockerfile.prod -t ghcr.io/YOUR_GITHUB_USERNAME/llm-diet-planner:latest .

# Push
docker push ghcr.io/YOUR_GITHUB_USERNAME/llm-diet-planner:latest
```

### Step 3: Configure in DigitalOcean
- **Registry provider**: GitHub Container Registry
- **Repository**: `YOUR_GITHUB_USERNAME/llm-diet-planner`
- **Image tag or digest**: `latest`
- **Credentials**: `YOUR_GITHUB_USERNAME:YOUR_GITHUB_TOKEN`
  - Create token at: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens

---

## ⚠️ RECOMMENDED: Use GitHub Source Instead

**For MVP, it's MUCH easier to deploy directly from GitHub!**

Instead of using Container Registry, choose "GitHub" as your source in DigitalOcean App Platform:

1. **Cancel the current setup** (or go back)
2. **Choose "GitHub"** as your source type
3. **Select your repository**
4. **DigitalOcean will automatically:**
   - Detect your `Dockerfile.prod`
   - Build the image for you
   - Deploy it automatically on every push
   
This is the approach recommended in `DEPLOYMENT.md` and `QUICK_START.md`.

If you want to switch to GitHub source, you don't need any of the registry information above!

