variable "project_name" {
  description = "Short name for resources"
  type        = string
  default     = "agentic-bank"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "westeurope"
}

variable "app_service_sku" {
  description = "App Service Plan SKU (B1, S1...)"
  type        = string
  default     = "B1"
}

variable "chainlit_demo_password" {
  description = "Header password expected by the API (X-Demo-Password)"
  type        = string
  default     = "demo"
  sensitive   = true
}
