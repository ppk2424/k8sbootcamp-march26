resource "kubernetes_namespace_v1" "vault" {
  metadata {
    name = "vault"
  }
}

resource "helm_release" "vault" {
  name       = "vault"
  repository = "https://helm.releases.hashicorp.com"
  chart      = "vault"
  namespace  = kubernetes_namespace_v1.vault.metadata[0].name

  values = [yamlencode({
    global = {
      enabled = true
    }

    server = {
      enabled = true

      # Dev mode - auto-unsealed, in-memory storage. Lab use only.
      dev = {
        enabled      = true
        devRootToken = "root"
      }

      resources = {
        requests = {
          memory = "128Mi"
          cpu    = "100m"
        }
        limits = {
          memory = "256Mi"
          cpu    = "250m"
        }
      }

      # ClusterIP - ALB ingress handles external traffic
      service = {
        type = "ClusterIP"
      }

      extraEnvironmentVars = {
        VAULT_LOG_LEVEL = "info"
      }
    }

    ui = {
      enabled = true
    }

    # ESO handles secret sync; sidecar injector not needed
    injector = {
      enabled = false
    }
  })]
}

resource "kubernetes_ingress_v1" "vault" {
  metadata {
    name      = "vault-ui-ingress"
    namespace = kubernetes_namespace_v1.vault.metadata[0].name

    annotations = {
      "alb.ingress.kubernetes.io/scheme"           = "internet-facing"
      "alb.ingress.kubernetes.io/target-type"      = "ip"
      "alb.ingress.kubernetes.io/healthcheck-path" = "/v1/sys/health?standbyok=true&uninitcode=200"
      "alb.ingress.kubernetes.io/listen-ports"     = "[{\"HTTP\": 80}]"
      "alb.ingress.kubernetes.io/group.name"       = "k8sbatch-shared-alb"
    }
  }

  spec {
    ingress_class_name = "alb"

    rule {
      host = "vault.${var.domain_name}"

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = "vault"
              port {
                number = 8200
              }
            }
          }
        }
      }
    }
  }

  depends_on = [helm_release.vault]
}
