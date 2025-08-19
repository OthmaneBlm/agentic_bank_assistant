# ---------- Naming helpers ----------
resource "random_string" "suffix" {
  length  = 5
  upper   = false
  lower   = true
  numeric = true
  special = false
}

locals {
  rg_name      = "${var.project_name}-rg"
  plan_name    = "${var.project_name}-plan"
  app_name     = "${var.project_name}-api-${random_string.suffix.result}"
  la_name      = "${var.project_name}-law"
  ai_name      = "${var.project_name}-appi"
}

# ---------- Resource Group ----------
resource "azurerm_resource_group" "rg" {
  name     = local.rg_name
  location = var.location
}

# ---------- Monitoring (lightweight) ----------
resource "azurerm_log_analytics_workspace" "law" {
  name                = local.la_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "appi" {
  name                = local.ai_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.law.id
}

# ---------- App Service Plan (Linux) ----------
resource "azurerm_service_plan" "plan" {
  name                = local.plan_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  os_type  = "Linux"
  sku_name = var.app_service_sku # e.g., B1
}

# ---------- Linux Web App ----------
resource "azurerm_linux_web_app" "api" {
  name                = local.app_name
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plan.id

  https_only = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on = true

    # Built-in Python stack
    application_stack {
      python_version = "3.11"
    }

    # Gunicorn+Uvicorn startup (FastAPI)
    # IMPORTANT: replace module path if your file layout differs
    # Binds to 0.0.0.0:8000
    app_command_line = "gunicorn -k uvicorn.workers.UvicornWorker agentic_bank.api.main:app --workers 2 --timeout 600 --bind=0.0.0.0:8000"
  }

  app_settings = {
    # Enables Oryx build during deployment from zip/src (if you use it)
    SCM_DO_BUILD_DURING_DEPLOYMENT           = "1"

    # If your app binds to 8000 (as above)
    WEBSITES_PORT                            = "8000"

    # Your app’s simple auth (used as X-Demo-Password header)
    CHAINLIT_DEMO_PASSWORD                   = var.chainlit_demo_password

    # App Insights
    APPLICATIONINSIGHTS_CONNECTION_STRING    = azurerm_application_insights.appi.connection_string
    APPLICATIONINSIGHTS_INSTRUMENTATIONKEY   = azurerm_application_insights.appi.instrumentation_key
  }

  logs {
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  lifecycle {
    ignore_changes = [
      app_settings["WEBSITE_RUN_FROM_PACKAGE"],  # if you zip-deploy later
      site_config[0].application_stack[0].python_version # minor patches
    ]
  }
}
