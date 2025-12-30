#!/bin/bash
# Script to build and push Docker image to registry
# Usage: ./build_and_push.sh [dockerhub|digitalocean|github]

set -e

REGISTRY_TYPE=${1:-dockerhub}

case $REGISTRY_TYPE in
  dockerhub)
    echo "Building and pushing to Docker Hub..."
    echo "Enter your Docker Hub username:"
    read DOCKERHUB_USERNAME
    
    # Login to Docker Hub
    docker login
    
    # Build image
    docker build -f Dockerfile.prod -t ${DOCKERHUB_USERNAME}/llm-diet-planner:latest .
    
    # Push image
    docker push ${DOCKERHUB_USERNAME}/llm-diet-planner:latest
    
    echo "✅ Image pushed successfully!"
    echo "Use this in DigitalOcean:"
    echo "  Repository: ${DOCKERHUB_USERNAME}/llm-diet-planner"
    echo "  Tag: latest"
    ;;
    
  digitalocean)
    echo "Building and pushing to DigitalOcean Container Registry..."
    echo "Enter your registry name (from DigitalOcean Container Registry):"
    read REGISTRY_NAME
    
    # Login to DO registry
    doctl registry login
    
    # Build and tag
    docker build -f Dockerfile.prod -t registry.digitalocean.com/${REGISTRY_NAME}/llm-diet-planner:latest .
    
    # Push
    docker push registry.digitalocean.com/${REGISTRY_NAME}/llm-diet-planner:latest
    
    echo "✅ Image pushed successfully!"
    echo "Use this in DigitalOcean:"
    echo "  Registry: DigitalOcean Container Registry"
    echo "  Repository: ${REGISTRY_NAME}/llm-diet-planner"
    echo "  Tag: latest"
    ;;
    
  *)
    echo "Usage: $0 [dockerhub|digitalocean]"
    exit 1
    ;;
esac

