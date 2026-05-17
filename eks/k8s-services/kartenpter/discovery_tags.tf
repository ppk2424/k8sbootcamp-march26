# Tag the private subnets so the EC2NodeClass `subnetSelectorTerms` finds them.
resource "aws_ec2_tag" "subnet_discovery" {
  for_each    = toset(data.aws_subnets.private.ids)
  resource_id = each.value
  key         = "karpenter.sh/discovery"
  value       = var.cluster_name
}

# Tag the EKS-managed cluster primary security group so the EC2NodeClass
# `securityGroupSelectorTerms` finds it. Karpenter-launched nodes will use
# this SG (same one the managed node group uses).
resource "aws_ec2_tag" "cluster_sg_discovery" {
  resource_id = data.aws_eks_cluster.cluster.vpc_config[0].cluster_security_group_id
  key         = "karpenter.sh/discovery"
  value       = var.cluster_name
}
