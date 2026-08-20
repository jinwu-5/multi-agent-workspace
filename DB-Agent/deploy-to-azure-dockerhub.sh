#!/bin/bash

echo "=== Azure Container Apps Deployment (Docker Hub) ==="

# Set variables with unique names to avoid conflicts
RESOURCE_GROUP="rg-db-agent-$(date +%s)"
LOCATION="eastus"
CONTAINER_APP_ENV="env-db-agent-$(date +%s)"
CONTAINER_APP_NAME="multi-db-agent"

echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "App Name: $CONTAINER_APP_NAME"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

# Get Docker Hub username
read -p "Enter your Docker Hub username: " DOCKER_USERNAME

# Validate username is not empty
if [ -z "$DOCKER_USERNAME" ]; then
    echo "❌ Docker Hub username cannot be empty!"
    exit 1
fi

DOCKER_IMAGE="$DOCKER_USERNAME/multi-db-agent:latest"

echo "Docker image: $DOCKER_IMAGE"
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI is not installed. Please install it first."
    exit 1
fi

# Login to Azure
echo "🔐 Logging into Azure..."
az login

# Create resource group
echo "📁 Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# Build image locally for linux/amd64 platform (fixes Mac ARM64 issue)
echo "🐳 Building Docker image for linux/amd64..."
docker buildx build --platform linux/amd64 -t "$DOCKER_IMAGE" . --load

# Login to Docker Hub
echo "🔐 Login to Docker Hub..."
echo "Please enter your Docker Hub password when prompted:"
docker login -u "$DOCKER_USERNAME"

# Push image to Docker Hub
echo "📤 Pushing image to Docker Hub..."
docker push "$DOCKER_IMAGE"

# Create Container Apps environment
echo "🌍 Creating Container Apps environment..."
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Create the container app (using public Docker Hub image)
echo "🚀 Creating container app..."
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image $DOCKER_IMAGE \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 0.25 \
  --memory 0.5Gi

# Get the app URL
echo "✅ Getting application URL..."
APP_URL=$(az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" --output tsv)

echo ""
echo "🎉 Deployment completed!"
echo "📱 Your app is deployed at: https://$APP_URL"
echo ""
echo "⚠️ IMPORTANT: Save these values for the configure-secrets.sh script:"
echo "RESOURCE_GROUP=$RESOURCE_GROUP"
echo "CONTAINER_APP_NAME=$CONTAINER_APP_NAME"
echo ""
echo "Next steps:"
echo "1. Update configure-secrets.sh with the resource group name above"
echo "2. Run: ./configure-secrets.sh"
echo "3. Test your app at: https://$APP_URL/health"