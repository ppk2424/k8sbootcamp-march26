# Week 4 - EKS Cluster with Terraform (Production Way)

## Topics Covered

**Real-World Repository Structure**
- Why do you never put everything in one repo — interdependencies cause failures at apply time
- How a real DevOps team structures repos: `eks-infra`, `monitoring`, `services` (load balancer controller, ArgoCD), `mono-deployment` (all microservices), `apm-deployment`, `data-jobs`, `test-automation`
- Each repo has a single scope — EKS repo only has EKS + add-ons, nothing else
- Why namespace creation cannot live in the same repo as EKS cluster creation — Kubernetes provider auth runs at plan time, not after cluster exists

**Enterprise Multi-Cluster Architecture (Interview Context)**
- Per-environment clusters (dev, staging, prod) as the baseline
- Dedicated clusters for: ML/data workloads, GitHub Actions self-hosted runners, internal tooling/IDP, agentic systems
- Netflix-style: same app cluster replicated across regions, connected via Transit Gateway (not VPC peering — doesn't scale beyond ~10 VPCs)
- Why Kubernetes is still the gold standard for scaling — 64K nodes, pod-level autoscaling, nothing else competes at this level

**Enterprise AWS Authentication (SSO + Rotating Credentials)**
- Nobody uses static access key + secret key in a real company — that is a red flag answer in interviews
- Azure AD (or Okta) as the Identity Provider — all employees get groups mapped to AWS roles
- Single Sign-On flow: login to Microsoft portal → click AWS app → switch account → get to console
- CLI flow: `aws sso configure` → `az login` (Azure CLI) → browser opens → login once → temporary token valid for 12 hours
- Credentials auto-populate into `~/.aws/credentials` as short-lived tokens, rotated automatically
- `aws-assume` tool for switching between dev/staging/prod profiles on the CLI

**Terraform for EKS — Production Setup**
- Using `tfenv` / `tfswitch` to manage multiple Terraform versions across repos — always pin your version
- S3 backend with `use_lockfile = true` for state locking (no DynamoDB needed in recent Terraform)
- State key naming convention: `<env>/<repo-name>/terraform.tfstate` — one key per repo per environment
- Why hardcode module versions: supply chain attacks — never use `latest`, one compromised package can affect every system pulling that tag
- Using the public `terraform-aws-modules/eks/aws` module (`~> 21.0`) — most starred, properly maintained, supports all node types
- Using `terraform-aws-modules/vpc/aws` for network — auto-handles required subnet tags for EKS

**VPC and Subnet Planning**
- Tags required on subnets for EKS to work: `kubernetes.io/cluster/<name> = shared`, `kubernetes.io/role/elb = 1` (public), `kubernetes.io/role/internal-elb = 1` (private)
- Without these tags, nodes won't connect and load balancer provisioning fails silently
- Single NAT gateway for dev/non-prod (`single_nat_gateway = true`) — save cost, not for production
- Nodes always on private subnets; load balancers on public subnets; database subnets separate

**EKS Module Configuration**
- `before_compute = true` on VPC CNI add-on — critical, without this nodes spin up before CNI is installed and never join the cluster
- `enable_cluster_creator_admin_permissions = true` — the Terraform-running IAM user/role gets admin access automatically
- EKS Access Entries for team members — role-based (not user-based), mapped from Azure AD groups to EKS policies
- Three access levels in practice: AWS IAM (account access) → EKS Access Entry (cluster authorization) → ArgoCD RBAC (developer-facing, app-level)
- In real teams: only DevOps engineers get `kubectl` access; developers get visibility through ArgoCD UI only

**Cluster Endpoint Access and VPN Whitelisting**
- Public+Private mode: `kubectl` works from your laptop, node traffic stays private
- Whitelist specific IP CIDR blocks on the public endpoint — your VPN IP range goes here
- VPN changes your outbound IP to a known range; that range is whitelisted in the cluster endpoint config
- This means: VPN connected → `kubectl` works; VPN disconnected → API server rejects you

**Database Migration Pattern**
- Never embed `flask db migrate` inside your app startup command in production
- Correct pattern: Kubernetes `Job` resource runs migration container once before deployment rollout
- In CI/CD pipeline: run migration Job → wait for success → then apply Deployment; if Job fails, halt pipeline
- Why: tables must exist before backend pods start; race condition if migration runs inside the container

**Application Overview (3-Tier Quiz App)**
- Flask backend, React frontend, PostgreSQL (RDS in production, docker-compose locally)
- Seed data pattern: migration script creates tables AND inserts initial data
- `initContainer` pattern shown: `wait-for-db` busybox container blocks backend startup until DNS resolves for the database service

**What's Coming Next Session**
- Full end-to-end app deployment to EKS
- AWS Load Balancer Controller install (replaces deprecated nginx ingress)
- Ingress resource, domain setup via Route53
- Secrets from AWS Secrets Manager (not base64 in manifests)
- IRSA vs Pod Identity — both explained with implementation

---

## Exercise — Step by Step

### 1. Set Up tfenv and Pin Terraform Version

```bash
# Install tfenv (macOS)
brew install tfenv

# Install and use a specific version
tfenv: install 1.12.1
tfenv use 1.12.1

# Verify
terraform version
```

### 2. Create Repository Folder Structure

```bash
mkdir -p eks-infra/network
mkdir -p eks-infra/eks
mkdir -p 3t-app/infra
mkdir -p 3t-app/k8s
```

### 3. Create S3 Backend Config (`eks/eks-infra/backend.tf`)

```hcl
terraform {
  backend "s3" {
    bucket       = "state-bucket-<your-account-id>"
    key          = "k8sbootcamp/eks/eks-infra/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

### 4. Create Terraform Version Constraint (`version.tf`)

```hcl
terraform {
  required_version = "1.12.1"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

### 5. Create VPC with Required EKS Tags (`network.tf`)

```hcl
variable "eks_cluster_name" {
  default = "eks-cluster"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "v6.6.0"

  name = "eks-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = true
  one_nat_gateway_per_az = false

  enable_dns_hostnames = true
  enable_dns_support   = true

  # Required for EKS load balancer discovery
  public_subnet_tags = {
    "kubernetes.io/cluster/${var.eks_cluster_name}" = "shared"
    "kubernetes.io/role/elb"                        = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${var.eks_cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"               = "1"
  }

  tags = {
    Terraform        = "true"
    terraform_source = "eks/eks-infra/network.tf"
  }
}
```

### 6. Deploy VPC First

```bash
cd eks/eks-infra
terraform init
terraform apply -target=module.vpc
```

> Wait for VPC, subnets, NAT gateway to complete before proceeding.

### 7. Create EKS Cluster Config (`eks.tf`)

```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.eks_cluster_name
  kubernetes_version = "1.33"

  addons = {
    kube-proxy = {}
    vpc-cni = {
      before_compute = true   # Critical — install CNI before nodes join
    }
    coredns = {}
    aws-ebs-csi-driver = {
      service_account_role_arn    = aws_iam_role.ebs_csi_driver.arn
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "PRESERVE"
    }
  }

  endpoint_public_access = true
  enable_cluster_creator_admin_permissions = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  eks_managed_node_groups = {
    eks_nodes = {
      ami_type       = "AL2023_x86_64_STANDARD"
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 5
      desired_size   = 2
    }
  }

  # Give a specific IAM user view access (use role ARN in production)
  access_entries = {
    readonly_user = {
      principal_arn = "arn:aws:iam::<account-id>:user/akhilesh"
      policy_associations = {
        view = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }

  tags = {
    Terraform = "true"
  }
}
```

### 8. Create IAM Role for EBS CSI Driver (`iam.tf`)

```hcl
resource "aws_iam_role" "ebs_csi_driver" {
  name = "${var.eks_cluster_name}-ebs-csi-driver"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = module.eks.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
          "${replace(module.eks.cluster_oidc_issuer_url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_csi_driver" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
  role       = aws_iam_role.ebs_csi_driver.name
}
```

### 9. Deploy EKS Cluster

```bash
terraform apply
# Takes 10–15 minutes
```

### 10. Configure kubectl and Verify

```bash
# Add cluster to kubeconfig
aws eks update-kubeconfig --region ap-south-1 --name eks-cluster

# Rename long ARN context to something readable
kubectl config rename-context \
  arn:aws:eks:ap-south-1:<account-id>:cluster/eks-cluster \
  eks

# Verify nodes are Ready
kubectl get nodes

# Check all system pods are Running
kubectl get pods -A
```

> You should see nodes as `Ready` and all add-on pods (`vpc-cni`, `kube-proxy`, `coredns`, `ebs-csi`) running.

### 11. Cost Management — Scale Down When Not Using

```bash
# Scale nodes to zero when done for the day
# Go to EKS → Compute → Node Group → Edit
# Set min=0, desired=0

# Also delete NAT gateway from console (biggest cost item)
# Next day: terraform apply will recreate NAT gateway automatically
```

> Do NOT delete the cluster between sessions — just scale nodes to zero and remove NAT gateway. Cluster itself costs ~$0.10/hr.

---

**Note:** Namespace creation, config maps, secrets, and app deployments go in a separate repo (`3t-app/infra`) — never in the EKS cluster repo. The Kubernetes provider authentication runs at plan time and will fail if the cluster doesn't exist yet.
