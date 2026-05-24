resource "helm_release" "karpenter" {
  name             = "karpenter"
  namespace        = var.karpenter_namespace
  repository       = "oci://public.ecr.aws/karpenter"
  chart            = "karpenter"
  version          = var.karpenter_version
  create_namespace = false

  set = [
    {
      name  = "settings.clusterName"
      value = var.cluster_name
    },
    {
      name  = "settings.interruptionQueue"
      value = aws_sqs_queue.karpenter.name
    },
    {
      name  = "serviceAccount.name"
      value = var.karpenter_sa
    },
    {
      name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
      value = aws_iam_role.karpenter_controller.arn
    },
    {
      name  = "controller.resources.requests.cpu"
      value = "200m"
    },
    {
      name  = "controller.resources.requests.memory"
      value = "256Mi"
    },
    {
      name  = "replicas"
      value = "1"
    },
  ]

  depends_on = [
    aws_iam_role_policy_attachment.karpenter_controller,
    aws_eks_access_entry.karpenter_node,
    aws_sqs_queue_policy.karpenter,
  ]
}
