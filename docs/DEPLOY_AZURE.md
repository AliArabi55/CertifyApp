# Deploy Certify to Azure App Service

Certify is a FastAPI app that stores data as files (no database). On App Service for Linux, the persistent `/home` volume holds projects and Gmail settings.

## What the deployment includes

| File | Purpose |
| --- | --- |
| [infra/main.bicep](../infra/main.bicep) | Linux App Service Plan and Web App (Python 3.12, HTTPS only, health check, persistent paths, login). |
| [startup.sh](../startup.sh) | Installs certificate fonts (best effort) and starts Gunicorn with one Uvicorn worker. |
| [.github/workflows/azure-deploy.yml](../.github/workflows/azure-deploy.yml) | Runs tests, then deploys on every push to `main`. |

App settings used by the code:

| Setting | Meaning |
| --- | --- |
| `CERTIFY_PASSWORD` / `CERTIFY_USERNAME` | Enables browser login (HTTP Basic). **Required for any public deployment**: the app has no user accounts and can send mail from the saved Gmail account. |
| `CERTIFY_DATA_DIR` | Where projects, PDFs, and send logs are stored. |
| `CERTIFY_CONFIG_DIR` | Where the Gmail credentials file is stored. |

## 1. Prerequisites

- An Azure subscription, the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), and a GitHub repository containing this project.
- Sign in: `az login`

## 2. Create the infrastructure

```powershell
$rg   = "certify-rg"
$app  = "certify-<your-unique-name>"   # must be globally unique
az group create -n $rg -l westeurope
az deployment group create -g $rg -f infra/main.bicep `
  -p webAppName=$app appPassword="<choose-a-strong-password>"
```

The command prints the app URL. Use a different region if you prefer.

## 3. First deployment (manual, optional)

```powershell
Compress-Archive -Path backend,frontend,requirements.txt,startup.sh -DestinationPath release.zip -Force
az webapp deploy -g $rg -n $app --src-path release.zip --type zip
```

Open the URL and sign in with `admin` and your password. `https://<app>.azurewebsites.net/health` stays public for health probes.

## 4. CI/CD with GitHub Actions (OIDC, no stored passwords)

1. Create an app registration and federated credential:

   ```powershell
   $sub = az account show --query id -o tsv
   $appId = az ad app create --display-name "certify-github" --query appId -o tsv
   az ad sp create --id $appId
   az role assignment create --assignee $appId --role "Website Contributor" `
     --scope "/subscriptions/$sub/resourceGroups/$rg"
   az ad app federated-credential create --id $appId --parameters '{
     "name": "github-production",
     "issuer": "https://token.actions.githubusercontent.com",
     "subject": "repo:<github-user>/<repo>:environment:production",
     "audiences": ["api://AzureADTokenExchange"]
   }'
   ```

2. In GitHub, create an environment named `production` (**Settings > Environments**).
3. Add repository **secrets**: `AZURE_CLIENT_ID` (the `$appId`), `AZURE_TENANT_ID` (`az account show --query tenantId -o tsv`), `AZURE_SUBSCRIPTION_ID`.
4. Add the repository **variable** `AZURE_WEBAPP_NAME` set to your app name.
5. Push to `main`. The workflow tests, packages, and deploys.

## 5. Use it

Connect Gmail in the **Send** tab using an App Password, as described in the README. Credentials are stored in plain text under `CERTIFY_CONFIG_DIR` (file mode 600) on the app's persistent storage.

## Operational notes

- **No database:** data lives on `/home`. To back it up, use `az webapp` file download via Kudu, or move `CERTIFY_DATA_DIR` to a mounted Azure Files share (`az webapp config storage-account add`). Moving to Azure SQL or Cosmos DB would require changes to `backend/app/storage.py`.
- **Single instance:** keep the plan at one instance. Send locks and logs are per process.
- **Large sends:** Azure's front end closes HTTP requests after about 230 seconds. The app waits 2 seconds between emails, so sending to more than roughly 100 recipients in one click can time out in the browser while the server continues. Re-run **Send**: addresses logged as sent are skipped.
- **Gmail limits:** Gmail rate limits still apply (about 500 messages per day for personal accounts).
- **Fonts:** Arial, Times New Roman, and Calibri map to Liberation Sans, Liberation Serif, and Carlito on Linux. Upload `.ttf` files for exact fonts.
- **Cost:** B1 is the smallest plan that supports Always On. Delete everything with `az group delete -n certify-rg`.
- **Password hardening:** for stronger secret handling, store `CERTIFY_PASSWORD` in Key Vault and reference it from the app setting, or switch to App Service Authentication (Entra ID).
