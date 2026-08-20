#!/bin/bash

echo "=== Configure Application Secrets and Environment Variables ==="

# These should match what you used in deploy-to-azure.sh
RESOURCE_GROUP="rg-db-agent"
CONTAINER_APP_NAME="multi-db-agent"

echo "Resource Group: $RESOURCE_GROUP"
echo "Container App: $CONTAINER_APP_NAME"
echo ""

# Prompt for environment variables
echo "Please enter your configuration values:"
echo ""

read -p "Enter your APP_API_KEY: " APP_API_KEY
echo ""

read -p "Enter your AZURE_OPENAI_ENDPOINT: " AZURE_OPENAI_ENDPOINT
echo ""

read -s -p "Enter your AZURE_OPENAI_API_KEY: " AZURE_OPENAI_API_KEY
echo ""
echo ""

read -p "Enter your AZURE_OPENAI_DEPLOYMENT (e.g., gpt-4.1-mini): " AZURE_OPENAI_DEPLOYMENT
echo ""

read -p "Enter your AZURE_OPENAI_API_VERSION (e.g., 2024-12-01-preview): " AZURE_OPENAI_API_VERSION
echo ""

read -s -p "Enter your PostgreSQL connection string (DVDRENTAL_PG_CONN): " DVDRENTAL_PG_CONN
echo ""
echo ""

read -s -p "Enter your MongoDB connection string (AIRBNB_MONGO_CONN): " AIRBNB_MONGO_CONN
echo ""
echo ""

read -p "Enter your AIRBNB_MONGO_DB (e.g., Mongo): " AIRBNB_MONGO_DB
echo ""

read -p "Enter your AIRBNB_MONGO_COLLECTION (e.g., Airbnb): " AIRBNB_MONGO_COLLECTION
echo ""

echo "🔐 Setting up secrets..."

# Create secrets
az containerapp secret set \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --secrets \
    app-api-key="$APP_API_KEY" \
    azure-openai-endpoint="$AZURE_OPENAI_ENDPOINT" \
    azure-openai-api-key="$AZURE_OPENAI_API_KEY" \
    dvdrental-pg-conn="$DVDRENTAL_PG_CONN" \
    airbnb-mongo-conn="$AIRBNB_MONGO_CONN"

echo "🌍 Setting up environment variables..."

# Update container app with environment variables
az containerapp update \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --set-env-vars \
    "APP_API_KEY=secretref:app-api-key" \
    "AZURE_OPENAI_ENDPOINT=secretref:azure-openai-endpoint" \
    "AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key" \
    "AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT" \
    "AZURE_OPENAI_API_VERSION=$AZURE_OPENAI_API_VERSION" \
    "DVDRENTAL_PG_CONN=secretref:dvdrental-pg-conn" \
    "AIRBNB_MONGO_CONN=secretref:airbnb-mongo-conn" \
    "AIRBNB_MONGO_DB=$AIRBNB_MONGO_DB" \
    "AIRBNB_MONGO_COLLECTION=$AIRBNB_MONGO_COLLECTION" \
    "DEFAULT_DATABASE=dvdrental"

echo ""
echo "✅ Configuration completed!"
echo ""
echo "🔄 Your app is restarting with new configuration..."
echo "⏱️ Wait about 30 seconds, then test your app"
echo ""

# Get the app URL again
APP_URL=$(az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" --output tsv)
echo "🌐 Test your app:"
echo "Health check: https://$APP_URL/health"
echo "Main app: https://$APP_URL"