
# Agentic Bank – LLM Router + Multi-Agent Demo

This project is a production-ready demo of an **agentic AI banking assistant** running on Azure, with:
- **Super Router** combining keyword, semantic, and LLM-based intent detection with topic shift handling.
- **Card Control Agent** for blocking/replacing cards using LLM-driven decision-making and tool calls.
- **Appointment Agent** for booking branch appointments using slot filling + tool calls.
- **FAQ Agent (RAG)** for knowledge-base queries.
- **Chainlit UI** with login, user profiles, and session history.



## Building Blocks

- API Layer: FastAPI, auth header (basic and deterministic), session lifecycle.

- Core: ProfileStore, ConversationMemory, InMemoryStore.
- Routing: EnsembleRouter + SuperRouter LLM.
- Agents: Card Control, Appointment, FAQ.
- Tools: Registered per agent (card APIs, appointment booking, FAQ KB search).
- External: Azure OpenAI (LLM), Bank APIs, Knowledge Base (to be provisioned and connected)
- Monitoring: Azure App Insights + Log Analytics (coming soon)

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
* App Service Plan (Linux B1 tier)
* Linux Web App running Chainlit with Key Vault secret references

### 1️⃣ Provision Infrastructure

```bash
cd infra/terraform
terraform init
terraform apply \
  -var "project_name=agenticbank" \
  -var "location=eastus" 
```
> Deploy `gpt-4o` and `text-embedding-3-large` manually in Azure AI Studio.

---

### 2️⃣ CI/CD via GitHub Actions

A workflow is included in `.github/workflows/main-agentic-banker-deploy.yml` that:

* Triggers on pushes to `main`
* Zips the repo
* Deploys to Azure Web App

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

```bash
src/agentic_bank/
  api/main.py     # FastAPI entrypoint
  core/      # LLM wrapper, memory, messages, tooling, logging
  router/   # keyword, semantic, LLM intent, topic shift, ensemble
  agents/
    cards/   # CardControlAgentLLM + tools + prompts
    appointment/ # AppointmentAgentLLM + tools + prompts
    faq/     # FAQ RAG agent
app_ui/
  app.py      # UI orchestration & routing
infra/terraform/ # Azure minimal infra
.github/workflows/main-agentic-bank-deploy.yml
requirements.txt
poetry.toml
```

---
## 📖 Next Steps

* Expand tool catalog and contracts.
* Add retrieval strategy for FAQ agent.
* Define router thresholds and clarify prompts.
* Integrate AAD authentication and Key Vault.