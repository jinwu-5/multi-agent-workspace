#!/bin/bash

echo "=== Testing Your Deployed Application ==="

RESOURCE_GROUP="rg-db-agent"
CONTAINER_APP_NAME="multi-db-agent"

# Get the app URL
APP_URL=$(az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --query "properties.configuration.ingress.fqdn" --output tsv)

if [ -z "$APP_URL" ]; then
    echo "❌ Could not get app URL. Make sure the app is deployed."
    exit 1
fi

echo "🌐 App URL: https://$APP_URL"
echo ""

# Test health endpoint
echo "🏥 Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "https://$APP_URL/health")

if [ "$HEALTH_RESPONSE" = "200" ]; then
    echo "✅ Health check passed!"
else
    echo "❌ Health check failed (HTTP $HEALTH_RESPONSE)"
fi

echo ""

# Test main endpoint (this might require API key)
echo "🔍 Testing main endpoint..."
MAIN_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "https://$APP_URL/")

if [ "$MAIN_RESPONSE" = "200" ] || [ "$MAIN_RESPONSE" = "401" ]; then
    echo "✅ Main endpoint is responding (HTTP $MAIN_RESPONSE)"
    if [ "$MAIN_RESPONSE" = "401" ]; then
        echo "ℹ️  Note: 401 means API key is required (this is expected)"
    fi
else
    echo "❌ Main endpoint issue (HTTP $MAIN_RESPONSE)"
fi

echo ""

# Show logs
echo "📋 Recent application logs:"
az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --tail 10

echo ""
echo "🎯 Your application is available at: https://$APP_URL"
echo ""
echo "📖 To view live logs, run:"
echo "az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --follow"