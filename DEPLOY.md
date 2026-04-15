# BDO Voice Studio — Deployment Guide

## Prerequisites

- Azure CLI installed and logged in (`az login`)
- Node.js 20+ (for local dev only)
- Python 3.11+ with venv (for local dev only)
- An Azure OpenAI resource with these models deployed:
  - `gpt-5.4` (or your GPT model for translation)
  - `gpt-audio-1.5` (for GPT Audio method)
  - `gpt-realtime-1.5` (for GPT Realtime method)
- An Azure Speech-enabled Cognitive Services resource (same resource works if it's a multi-service AI Services resource)
- An Azure Storage Account with a blob container for audio files

---

## 1. Create Azure Resources

```bash
# Variables — customize these
RG="rg-bdo-voice-studio"
LOCATION="swedencentral"
ACR_NAME="bdovoiceacr"
APP_NAME="bdo-voice-studio"
ENV_NAME="bdo-voice-env"

# Resource Group
az group create --name $RG --location $LOCATION

# Container Registry
az acr create --name $ACR_NAME --resource-group $RG --sku Basic --admin-enabled true

# Container Apps Environment
az containerapp env create --name $ENV_NAME --resource-group $RG --location $LOCATION
```

## 2. Build & Push Docker Image

```bash
cd /path/to/taglishtranslate

az acr build \
  --registry $ACR_NAME \
  --resource-group $RG \
  --image bdo-voice-studio:latest \
  --file Dockerfile .
```

## 3. Deploy Container App

```bash
# Get ACR credentials
ACR_USER=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASS=$(az acr credential show --name $ACR_NAME --query 'passwords[0].value' -o tsv)

# Create Container App
az containerapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --environment $ENV_NAME \
  --image ${ACR_NAME}.azurecr.io/bdo-voice-studio:latest \
  --registry-server ${ACR_NAME}.azurecr.io \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --system-assigned \
  --target-port 5000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    "AZURE_OPENAI_ENDPOINT=https://<your-openai-resource>.openai.azure.com/openai/v1/" \
    "AZURE_OPENAI_DEPLOYMENT=gpt-5.4" \
    "AZURE_OPENAI_AUDIO_DEPLOYMENT=gpt-audio-1.5" \
    "AZURE_OPENAI_REALTIME_DEPLOYMENT=gpt-realtime-1.5" \
    "AZURE_SPEECH_RESOURCE_ID=/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<resource-name>" \
    "AZURE_SPEECH_REGION=swedencentral" \
    "AZURE_SPEECH_VOICE=fil-PH-BlessicaNeural" \
    "AZURE_STORAGE_ACCOUNT_URL=https://<storage-account>.blob.core.windows.net" \
    "AZURE_STORAGE_CONTAINER_NAME=taglish"
```

## 4. Get Managed Identity Principal ID

```bash
PRINCIPAL_ID=$(az containerapp show --name $APP_NAME --resource-group $RG --query identity.principalId -o tsv)
echo "Principal ID: $PRINCIPAL_ID"
```

## 5. Assign RBAC Roles

Replace `<cog-services-resource-id>` and `<storage-account-resource-id>` with full resource IDs.

```bash
COG_SCOPE="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<resource-name>"
STORAGE_SCOPE="/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<storage-name>"

# OpenAI access (GPT models)
az role assignment create \
  --assignee-object-id $PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope $COG_SCOPE

# Speech TTS access
az role assignment create \
  --assignee-object-id $PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services User" \
  --scope $COG_SCOPE

# Blob Storage access (audio upload)
az role assignment create \
  --assignee-object-id $PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope $STORAGE_SCOPE
```

> **Note:** You need Owner or User Access Administrator role to assign RBAC. If using the portal: go to the resource → Access control (IAM) → Add role assignment → Managed identity → select the Container App.

### Roles Summary

| Role | Resource | Purpose |
|------|----------|---------|
| Cognitive Services OpenAI User | AI Services / OpenAI resource | GPT-5.4, gpt-audio-1.5, gpt-realtime-1.5 |
| Cognitive Services User | AI Services / OpenAI resource | Azure Speech TTS token |
| Storage Blob Data Contributor | Storage Account | Upload generated audio |

## 6. Verify Deployment

```bash
# Get app URL
az containerapp show --name $APP_NAME --resource-group $RG \
  --query properties.configuration.ingress.fqdn -o tsv

# Test health
curl https://<fqdn>/api/health
```

---

## Update App After Code Changes

```bash
cd /path/to/taglishtranslate

# 1. Build new image
az acr build \
  --registry $ACR_NAME \
  --resource-group $RG \
  --image bdo-voice-studio:latest \
  --file Dockerfile .

# 2. Deploy new image
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --image ${ACR_NAME}.azurecr.io/bdo-voice-studio:latest
```

## Update Environment Variables

```bash
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --set-env-vars "KEY=value"
```

## View Logs

```bash
az containerapp logs show \
  --name $APP_NAME \
  --resource-group $RG \
  --follow
```

## Local Development

```bash
# Terminal 1: Backend
cd taglishtranslate
.venv/bin/python app.py

# Terminal 2: Frontend (hot reload)
cd taglishtranslate/frontend
npx vite --host

# Open http://localhost:5173
```
