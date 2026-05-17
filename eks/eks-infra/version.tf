terraform {
 
  required_version = "1.12.1"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# terraform {
#     backend "s3" {
#         bucket         = "state-bucket-879381241087"
#         key            = "k8sbootcamp-march26/ghoidc/terraform.tfstate"
#         region         = "ap-south-1"
#         encrypt        = true
#         use_lockfile = true
#     }
# }