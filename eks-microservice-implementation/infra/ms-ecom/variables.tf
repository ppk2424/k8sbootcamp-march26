variable "cluster_name" {
  default = "eks-cluster"
}

variable "region" {
  default = "ap-south-1"
}

variable "namespace" {
  description = "Namespace where the ecommerce app is deployed"
  default     = "ecommerce"
}

variable "ingress_name" {
  default = "ecommerce-ingress"
}

variable "ingress_class_name" {
  default = "alb"
}

variable "alb_group_name" {
  description = "ALB group name — shared with other ingresses on the same ALB"
  default     = "k8sbatch-shared-alb"
}

variable "host" {
  description = "Hostname routed by the ingress"
  default     = "shop.livingdevops.org"
}

variable "api_gateway_service_name" {
  default = "api-gateway"
}

variable "frontend_service_name" {
  default = "frontend"
}

variable "service_port" {
  default = 80
}
