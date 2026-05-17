resource "kubernetes_ingress_v1" "ecommerce" {
  metadata {
    name      = var.ingress_name
    namespace = var.namespace

    annotations = {
      "alb.ingress.kubernetes.io/scheme"           = "internet-facing"
      "alb.ingress.kubernetes.io/target-type"      = "ip"
      "alb.ingress.kubernetes.io/listen-ports"     = jsonencode([{ HTTP = 80 }])
      "alb.ingress.kubernetes.io/group.name"       = var.alb_group_name
      "alb.ingress.kubernetes.io/healthcheck-path" = "/health"
    }
  }

  spec {
    ingress_class_name = var.ingress_class_name

    rule {
      host = var.host

      http {
        path {
          path      = "/api"
          path_type = "Prefix"
          backend {
            service {
              name = var.api_gateway_service_name
              port {
                number = var.service_port
              }
            }
          }
        }

        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = var.frontend_service_name
              port {
                number = var.service_port
              }
            }
          }
        }
      }
    }
  }
}
