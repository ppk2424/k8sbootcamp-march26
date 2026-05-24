# Explicit DNS for Vault UI/API. The argocd stack may also define *.livingdevops.org;
# this record guarantees vault.<domain> resolves even if the wildcard is missing or stale.

data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# ALB controller populates ingress.status asynchronously after create.
resource "time_sleep" "wait_for_vault_ingress" {
  depends_on      = [kubernetes_ingress_v1.vault]
  create_duration = "60s"
}

data "kubernetes_ingress_v1" "vault" {
  metadata {
    name      = kubernetes_ingress_v1.vault.metadata[0].name
    namespace = kubernetes_ingress_v1.vault.metadata[0].namespace
  }

  depends_on = [time_sleep.wait_for_vault_ingress]
}

resource "aws_route53_record" "vault" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "vault.${var.domain_name}"
  type    = "A"

  alias {
    name                   = data.kubernetes_ingress_v1.vault.status[0].load_balancer[0].ingress[0].hostname
    zone_id                = var.aws_alb_zoneid
    evaluate_target_health = true
  }

  depends_on = [data.kubernetes_ingress_v1.vault]
}
