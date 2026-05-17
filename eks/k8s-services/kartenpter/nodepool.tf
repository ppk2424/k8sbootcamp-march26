# Karpenter custom resources. The kubectl provider (gavinbunney/kubectl) is used
# instead of kubernetes_manifest because it does not require the CRDs to exist
# at plan time — they are installed by the helm_release above.

resource "kubectl_manifest" "ec2nodeclass_default" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata = {
      name = "default"
    }
    spec = {
      amiFamily = "AL2023"
      amiSelectorTerms = [
        { alias = "al2023@latest" },
      ]
      role = aws_iam_role.karpenter_node.name
      subnetSelectorTerms = [
        {
          tags = {
            "karpenter.sh/discovery" = var.cluster_name
          }
        },
      ]
      securityGroupSelectorTerms = [
        {
          tags = {
            "karpenter.sh/discovery" = var.cluster_name
          }
        },
      ]
      tags = {
        "karpenter.sh/discovery" = var.cluster_name
      }
    }
  })

  depends_on = [helm_release.karpenter]
}

resource "kubectl_manifest" "nodepool_default" {
  yaml_body = yamlencode({
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "default"
    }
    spec = {
      template = {
        spec = {
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "default"
          }
          requirements = [
            {
              key      = "karpenter.sh/capacity-type"
              operator = "In"
              values   = ["spot", "on-demand"]
            },
            {
              key      = "kubernetes.io/arch"
              operator = "In"
              values   = ["amd64"]
            },
            {
              key      = "kubernetes.io/os"
              operator = "In"
              values   = ["linux"]
            },
            {
              key      = "karpenter.k8s.aws/instance-category"
              operator = "In"
              values   = ["c", "m", "r"]
            },
            {
              key      = "karpenter.k8s.aws/instance-generation"
              operator = "Gt"
              values   = ["2"]
            },
          ]
          expireAfter = "720h"
        }
      }
      limits = {
        cpu = 100
      }
      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "1m"
      }
    }
  })

  depends_on = [kubectl_manifest.ec2nodeclass_default]
}
