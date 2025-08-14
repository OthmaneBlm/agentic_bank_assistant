output "resource_group" { value = azurerm_resource_group.rg.name }
output "webapp_name"    { value = azurerm_linux_web_app.app.name }
output "webapp_url"     { value = azurerm_linux_web_app.app.default_hostname }
output "openai_endpoint"{ value = azurerm_cognitive_account.openai.endpoint }
output "key_vault_name" { value = azurerm_key_vault.kv.name }
