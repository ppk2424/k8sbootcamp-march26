# Allow kubelets on Karpenter-launched EC2 instances to join the cluster.
# EKS 1.33 uses Access Entries (not aws-auth) — type EC2_LINUX maps the node role.
resource "aws_eks_access_entry" "karpenter_node" {
  cluster_name  = var.cluster_name
  principal_arn = aws_iam_role.karpenter_node.arn
  type          = "EC2_LINUX"
}
