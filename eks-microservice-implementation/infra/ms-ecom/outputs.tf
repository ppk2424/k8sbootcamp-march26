output "ingress_name" {
  value = kubernetes_ingress_v1.ecommerce.metadata[0].name
}

output "ingress_namespace" {
  value = kubernetes_ingress_v1.ecommerce.metadata[0].namespace
}

output "ingress_host" {
  value = var.host
}

output "alb_hostname" {
  description = "ALB hostname assigned by aws-load-balancer-controller (populated after the ALB provisions)"
  value       = try(kubernetes_ingress_v1.ecommerce.status[0].load_balancer[0].ingress[0].hostname, null)
}
