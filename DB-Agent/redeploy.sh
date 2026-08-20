# Create a new file: redeploy.sh
#!/bin/bash
echo "Redeploying multi-db-agent..."

# Build and push updated image
docker buildx build --platform linux/amd64 -t jwu769/multi-db-agent:latest . --push

# Update existing container app
az containerapp update \
  --name multi-db-agent \
  --resource-group rg-db-agent \
  --image jwu769/multi-db-agent:latest

echo "Redeployment completed!"