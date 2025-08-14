variable "project_name" {
  description = "Short, unique name used to prefix resources."
  type        = string
}

variable "location" {
  description = "Azure region (must support Azure OpenAI, e.g., eastus)."
  type        = string
  default     = "eastus"
}

variable "openai_sku" {
  description = "Azure OpenAI SKU"
  type        = string
  default     = "S0"
}

variable "webapp_sku" {
  description = "App Service Plan SKU"
  type        = string
  default     = "B1"
}

variable "chainlit_demo_password" {
  description = "Password for Chainlit demo login."
  type        = string
  default     = "demo"
}

variable "openai_chat_deployment" {
  description = "Name of your Azure OpenAI Chat model deployment (create this separately)."
  type        = string
  default     = "gpt-4o"
}

variable "openai_embedding_deployment" {
  description = "Name of your Azure OpenAI Embedding model deployment."
  type        = string
  default     = "text-embedding-3-large"
}
