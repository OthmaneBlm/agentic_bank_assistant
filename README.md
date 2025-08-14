
# Agentic Bank – LLM Router + Multi-Agent Demo

This project is a production-ready demo of an **agentic AI banking assistant** running on Azure, with:
- **Super Router** combining keyword, semantic, and LLM-based intent detection with topic shift handling.
- **Card Control Agent** for blocking/replacing cards using LLM-driven decision-making and tool calls.
- **Appointment Agent** for booking branch appointments using slot filling + tool calls.
- **FAQ Agent (RAG)** for knowledge-base queries.
- **Chainlit UI** with login, user profiles, and session history.

---

## 🚀 Quick Start (Local)

### 1️⃣ Requirements
- Python **3.11**
- [Poetry](https://python-poetry.org/) for dependency management
- Node is **not required** for Chainlit

### 2️⃣ Install dependencies
```bash
poetry install
````

### 3️⃣ Configure environment variables

Create `.env` at the repo root:

```
AZURE_OPENAI_ENDPOINT=https://<your-aoai>.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-08-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# Chainlit auth
CHAINLIT_DEMO_PASSWORD=demo
CHAINLIT_JWT_SECRET=<any-random-string>
```

### 4️⃣ Run locally

Terminal A (optional API backend if needed):

```bash
poetry run uvicorn agentic_bank.api.main:app --reload --port 8000
```

Terminal B (Chainlit UI):

```bash
cd chainlit
poetry run chainlit run app.py --host 0.0.0.0 --port 8001
```

Open: **[http://localhost:8001](http://localhost:8001)**
Login with any username and password=`demo` (change in `.env`).

---

## ☁ Azure Deployment (Minimal Setup)

We provide **Terraform** in `infra/terraform` to provision:

* Resource group
* Azure OpenAI account
* Key Vault (stores secrets)
* App Service Plan (Linux B1 tier)
* Linux Web App running Chainlit with Key Vault secret references

### 1️⃣ Provision Infrastructure

```bash
cd infra/terraform
terraform init
terraform apply \
  -var "project_name=agenticbank" \
  -var "location=eastus" \
  -var "chainlit_demo_password=demo" \
  -var "openai_chat_deployment=gpt-4o" \
  -var "openai_embedding_deployment=text-embedding-3-large"
```

> **Note:** Terraform creates the OpenAI account but **not model deployments**.
> Deploy `gpt-4o` and `text-embedding-3-large` manually in Azure AI Studio (names must match above).

---

### 2️⃣ CI/CD via GitHub Actions

A workflow is included in `.github/workflows/deploy.yml` that:

* Triggers on pushes to `main`
* Zips the repo
* Deploys to Azure Web App

#### GitHub Secrets required:

* `AZURE_CREDENTIALS` — JSON from:

```bash
az ad sp create-for-rbac \
  --name "gh-agentic-bank-deployer" \
  --role contributor \
  --scopes /subscriptions/<SUB_ID>/resourceGroups/$(terraform output -raw resource_group) \
  --sdk-auth
```

* `AZURE_WEBAPP_NAME` — from `terraform output -raw webapp_name`
* `AZURE_RESOURCE_GROUP` — from `terraform output -raw resource_group`

---

## 🔧 Configuration & Secrets

Secrets are stored in **Azure Key Vault** and injected into the Web App via Key Vault references:

* `AZURE_OPENAI_API_KEY`
* `AZURE_OPENAI_ENDPOINT`
* `CHAINLIT_JWT_SECRET`
* `CHAINLIT_DEMO_PASSWORD`

Non-secret app settings:

* `AZURE_OPENAI_API_VERSION`
* `AZURE_OPENAI_DEPLOYMENT`
* `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

---

## 📂 Project Structure

```
src/agentic_bank/
  core/          # LLM wrapper, memory, messages, tooling, logging
  router/        # keyword, semantic, LLM intent, topic shift, ensemble
  agents/
    cards/       # CardControlAgentLLM + tools + prompts
    appointment/ # AppointmentAgentLLM + tools + prompts
    faq/         # FAQ RAG agent
chainlit/
  app.py         # UI orchestration & routing
infra/terraform/ # Azure minimal infra
.github/workflows/deploy.yml
```

---

## 🛠 Troubleshooting

* **Auth error:** `ValueError: You must provide a JWT secret…`
  → Add `CHAINLIT_JWT_SECRET` to `.env`, or run `chainlit create-secret`.

* **Port in use (8000/8001):**
  → Change ports or stop the running process.

* **Azure 400 Bad Request:**
  → Ensure your Azure deployment names match environment variables.

---

## 📈 Next Steps

* Add Application Insights for telemetry.
* Store conversation history in Azure Storage or Cosmos DB.
* Add Terraform for AOAI deployment creation.
* Containerize the app and deploy from ACR.

---
