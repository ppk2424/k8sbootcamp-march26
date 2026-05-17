module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = "eks-cluster"
  kubernetes_version = "1.33"

  addons = {
    coredns                = {}
    # eks-pod-identity-agent = {
    #   before_compute = true
    # }
    kube-proxy             = {}
    vpc-cni                = {
      before_compute = true
    }
    aws-ebs-csi-driver = {
      service_account_role_arn = aws_iam_role.ebs_csi_driver.arn
      # addon_version               = "v1.37.0-eksbuild.1"
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "PRESERVE"
    }
  }

  # Optional
  endpoint_public_access = true

  # Optional: Adds the current caller identity as an administrator via cluster access entry
  enable_cluster_creator_admin_permissions = true

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets

  # EKS Managed Node Group(s)
  eks_managed_node_groups = {
    eks_nodes = {
      # Starting on 1.30, AL2023 is the default AMI type for EKS managed node groups
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = ["t3.medium"]

      min_size     = 2
      max_size     = 5
      desired_size = 2
    }
  }

  # access_entries = {
  #   # One access entry with a policy associated
  #   example = {
  #   principal_arn = "arn:aws:iam::879381241087:user/akhilesh"
  #   # principal_arn = "arn:aws:iam::879381241087:role/ec2-admin"

  #     policy_associations = {
  #       example = {
  #         policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
  #         access_scope = {
  #           # namespaces = ["default"]
  #           type       = "cluster"
  #         }
  #       }
  #     }
  #   }
  # }

  tags = {
    Terraform   = "true"
  }
}