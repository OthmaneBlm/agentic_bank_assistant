output "resource_group" {
  value = azurerm_resource_group.rg.name
}

output "webapp_name" {
  value = azurerm_linux_web_app.api.name
}

output "webapp_url" {
  value = "https://${azurerm_linux_web_app.api.default_hostname}"
}

output "app_insights_portal_url" {
  value = azurerm_application_insights.appi.app_id
  description = "Use in Azure Portal to find the App Insights resource"
}
