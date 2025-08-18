data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "rg" {
  name     = "${var.project_name}-rg"
  location = var.location
}

resource "azurerm_cognitive_account" "openai" {
  name                = "${var.project_name}-aoai"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  kind                = "OpenAI"
  sku_name            = var.openai_sku
  custom_subdomain_name = "${var.project_name}-aoai"
}

resource "azurerm_key_vault" "kv" {
  name                        = "${var.project_name}-kv"
  location                    = var.location
  resource_group_name         = azurerm_resource_group.rg.name
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 7
  purge_protection_enabled    = true
}

resource "random_password" "chainlit_jwt" {
  length  = 48
  special = true
}

resource "azurerm_key_vault_secret" "openai_key" {
  name         = "AZURE-OPENAI-API-KEY"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.kv.id
}
resource "azurerm_key_vault_secret" "openai_endpoint" {
  name         = "AZURE-OPENAI-ENDPOINT"
  value        = azurerm_cognitive_account.openai.endpoint
  key_vault_id = azurerm_key_vault.kv.id
}
resource "azurerm_key_vault_secret" "chainlit_jwt" {
  name         = "CHAINLIT-JWT-SECRET"
  value        = random_password.chainlit_jwt.result
  key_vault_id = azurerm_key_vault.kv.id
}
resource "azurerm_key_vault_secret" "demo_pwd" {
  name         = "CHAINLIT-DEMO-PASSWORD"
  value        = var.chainlit_demo_password
  key_vault_id = azurerm_key_vault.kv.id
}

resource "azurerm_service_plan" "asp" {
  name                = "${var.project_name}-plan"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  os_type             = "Linux"
  sku_name            = var.webapp_sku
}

resource "azurerm_linux_web_app" "app" {
  name                = "${var.project_name}-web"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  service_plan_id     = azurerm_service_plan.asp.id
  https_only          = true

  identity { type = "SystemAssigned" }

  site_config {
    application_stack { python_version = "3.11" }
    app_command_line = "chainlit run chainlit/app.py --host 0.0.0.0 --port 8000"
  }

  app_settings = {
    WEBSITES_PORT                     = "8000"
    SCM_DO_BUILD_DURING_DEPLOYMENT    = "true"

    AZURE_OPENAI_ENDPOINT             = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.openai_endpoint.id})"
    AZURE_OPENAI_API_KEY              = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.openai_key.id})"
    AZURE_OPENAI_API_VERSION          = "2024-08-01-preview"
    AZURE_OPENAI_DEPLOYMENT           = var.openai_chat_deployment
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = var.openai_embedding_deployment

    CHAINLIT_DEMO_PASSWORD            = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.demo_pwd.id})"
    CHAINLIT_JWT_SECRET               = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.chainlit_jwt.id})"
  }
}

resource "azurerm_key_vault_access_policy" "webapp_policy" {
  key_vault_id = azurerm_key_vault.kv.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_web_app.app.identity[0].principal_id

  secret_permissions = ["Get", "List"]
}
