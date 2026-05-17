variable "cluster_name" {
  default = "eks-cluster"
}

variable "region" {
  default = "ap-south-1"
}

# Vault URL terraform talks to. Default assumes Vault is port-forwarded:
#   kubectl port-forward -n vault svc/vault 8200:8200
variable "vault_addr" {
  description = "Vault server address terraform writes secrets to (e.g. http://localhost:8200 with port-forward)"
  default     = "http://localhost:8200"
}

variable "vault_token" {
  description = "Vault auth token. Default is the dev-mode root token from eks/k8s-services/vault-eso/."
  default     = "root"
  sensitive   = true
}

# Address ESO uses to reach Vault from inside the cluster.
variable "vault_in_cluster_addr" {
  description = "Vault address as seen from inside the cluster (used by the ClusterSecretStore)"
  default     = "http://vault.vault.svc.cluster.local:8200"
}

variable "enable_eso_secrets" {
  description = "When true, also create the ClusterSecretStore + ExternalSecrets that bind ESO to Vault and materialise K8s secrets in the ecommerce namespace. ESO CRDs and the ecommerce namespace must already exist."
  type        = bool
  default     = false
}

variable "ecommerce_namespace" {
  default = "ecommerce"
}

variable "external_secrets_namespace" {
  default = "external-secrets"
}

variable "db_user" {
  default = "ecommerce_user"
}

variable "rabbitmq_user" {
  default = "rabbitmq"
}

# External-service credentials. Override via tfvars / -var when wiring real values.
variable "razorpay_key_id" {
  default   = "rzp_test_placeholder"
  sensitive = true
}

variable "razorpay_key_secret" {
  default   = "placeholder_secret_key"
  sensitive = true
}

variable "razorpay_webhook_secret" {
  default   = "whsec_placeholder"
  sensitive = true
}

variable "aws_access_key_id" {
  default   = "AKIAIOSFODNN7EXAMPLE"
  sensitive = true
}

variable "aws_secret_access_key" {
  default   = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  sensitive = true
}
