# Route53 and ACM Certificate Configuration

# Get the hosted zone for the domain
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# # Create ACM certificate for the subdomain
# data "aws_acm_certificate" "argocd_cert" {
#   domain   = "argocd.${var.domain_name}"
#   statuses = ["ISSUED"]
  
# }

# Create Route53 alias record to point subdomain to ALB

# ALB controller populates ingress.status asynchronously after create.
resource "time_sleep" "wait_for_argocd_ingress" {
  depends_on      = [kubernetes_ingress_v1.argocd]
  create_duration = "60s"
}

data "kubernetes_ingress_v1" "argocd" {
  metadata {
    name      = kubernetes_ingress_v1.argocd.metadata[0].name
    namespace = kubernetes_ingress_v1.argocd.metadata[0].namespace
  }

  depends_on = [time_sleep.wait_for_argocd_ingress]
}

resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "*.${var.domain_name}"
  type    = "A"

  alias {
    name                   = data.kubernetes_ingress_v1.argocd.status[0].load_balancer[0].ingress[0].hostname
    zone_id                = var.aws_alb_zoneid
    evaluate_target_health = true
  }

  depends_on = [data.kubernetes_ingress_v1.argocd]
}


