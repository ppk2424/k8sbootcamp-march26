variable "cluster_name" {
  default = "eks-cluster"
}

variable "region" {
  default = "ap-south-1"
}

variable "vpc_name" {
  default = "eks-vpc"
}

variable "karpenter_namespace" {
  default = "kube-system"
}

variable "karpenter_sa" {
  default = "karpenter"
}

variable "karpenter_version" {
  default = "1.5.0"
}
