# Week 6 - AWS Load Balancer Controller, IRSA, and Ingress

## Topics Covered

**Recap and State Management Gotchas**
- When you destroy and recreate infra, VPC ID changes but the name tag stays the same — always use `name` tag filter in data sources, not hardcoded IDs
- AWS Secrets Manager enforces a 7-day minimum retention — you cannot reuse the same secret name until 7 days after deletion; force-delete with the CLI when needed
- Terraform state drifts when you delete resources manually via Lens/kubectl — state and cluster diverge; Terraform is not ideal for resources that change frequently (deployments); use ArgoCD for those

**Terraform vs ArgoCD vs Helm — When to Use What**
- Rule of thumb: anything that changes with every feature release (deployment image) → ArgoCD; everything static (namespaces, configmaps, secrets, ingress, cert config) → Terraform
- You can have both in sync simultaneously: tag every image with both `latest` and the Git commit SHA; Terraform always deploys `latest` so it never changes; ArgoCD rotates using the commit SHA tag
- Two separate pipelines: one for infra (Terraform), one for app (ArgoCD/Helm) — never mix them in the same pipeline job
- Helm chart wraps your deployment + service + ingress; ArgoCD watches the Helm chart and applies it

**Ingress Fundamentals**
- Why not `type: LoadBalancer` on every service: each service creates its own ALB → 25 microservices × 5 environments = 125 ALBs → excessive cost, 125 certificates to manage, 125 exposure points
- Ingress is not a device or service — it is a routing rules config; a controller reads those rules and provisions one ALB
- One Ingress resource can cover all your services via path-based routing; one ALB handles all traffic
- ALB group: if you use one Ingress per service (preferred for clarity), annotate all of them with the same `alb.ingress.kubernetes.io/group.name` — all routes land on a single ALB
- ALB limit: maximum 200 routing rules per ALB — sufficient for 99% of use cases; beyond that, look at Kong, Traefik, or AWS API Gateway

**nginx Ingress Controller — Why It Was Retired**
- Was maintained by two open source contributors who stopped supporting it after March 2026 — no more security patches
- Unpatched ingress controller = open security black hole in production; you cannot use an unpatched component
- Migration path: switch from nginx ingress class to `alb` ingress class, move SSL termination from inside the cluster (cert-manager + Let's Encrypt) to ALB + ACM, change NLB to ALB, update a handful of annotations — roughly 5 changes, can be done in one `kubectl apply`

**SSL Termination — Two Approaches**
- Old way (nginx): SSL termination happens inside the cluster; NLB is a passthrough; cert-manager + Let's Encrypt manages certificates inside Kubernetes; HTTPS all the way to the pod
- New way (ALB + ACM): SSL terminates at the ALB layer; traffic inside the cluster is HTTP; ACM auto-renews certificates; simpler to manage; AWS WAF integrates at the ALB layer (not possible with cluster-internal termination)
- NLB works at layer 4 (network) — does not understand HTTP/HTTPS, cannot terminate SSL
- ALB works at layer 7 (application) — understands HTTP/HTTPS, supports SSL termination, path routing, host routing

**AWS Load Balancer Controller**
- Software that runs inside your cluster and watches Ingress objects; when an Ingress is created, it calls the AWS API to provision an ALB with the correct rules
- Installed via Helm chart — one install per cluster, lives in `kube-system` namespace
- Creates an IngressClass called `alb` — you reference this in every Ingress resource
- Needs IAM permissions to create and manage ALBs, query subnets, manage security groups, list certificates — these are defined in a JSON policy document from the AWS docs

**IRSA — IAM Roles for Service Accounts**
- Problem: the load balancer controller pod needs AWS IAM permissions, but pods don't have AWS credentials by default
- Solution chain: OIDC provider (built into every EKS cluster) → IAM Identity Provider in AWS (trusts the cluster's OIDC) → IAM Role with trust policy allowing the OIDC to assume it → Kubernetes Service Account annotated with the IAM Role ARN → pods using that service account inherit the role
- Trust relationship conditions: `StringEquals` on `<oidc>:sub = system:serviceaccount:kube-system:aws-load-balancer-controller` — only that specific service account can assume the role, nobody else
- Annotations: `eks.amazonaws.com/role-arn: arn:aws:iam::<account>:role/<role-name>` on the Kubernetes service account
- Terraform: fetch OIDC URL dynamically from `data.aws_eks_cluster.main.identity[0].oidc[0].issuer` — no hardcoding
- Pod Identity is the newer alternative with better security token handling — same concept, different mechanics; covered in a later session

**Subnet Tags Required for ALB**
- Public subnets need: `kubernetes.io/role/elb = 1`
- Private subnets need: `kubernetes.io/role/internal-elb = 1`
- Both need: `kubernetes.io/cluster/<cluster-name> = shared`
- Without these tags the load balancer controller cannot discover which subnets to place the ALB in — silently fails

**Database Migration Pattern (Finalized)**
- Migration runs as a Kubernetes `Job` — one-time activity, exits on completion
- Sequence in CI/CD pipeline: build image → push to ECR → run migration Job → wait for Job success → apply backend Deployment → apply frontend Deployment
- If migration Job fails: pipeline stops, no new deployment rolls out
- Schema deletion strategy in blue/green: never delete a column immediately; deprecate it (stop writing to it), deploy 2–3 more releases, only then drop it — old pods running during rolling update are never broken by a missing column they expect

---

## Exercise — Step by Step

### 1. Force-Delete Locked Secrets Manager Secrets

If you hit the 7-day retention error on re-apply:

```bash
# Force delete (bypasses retention period)
aws secretsmanager delete-secret \
  --secret-id "3t-app/db-credentials" \
  --force-delete-without-recovery \
  --region ap-south-1

aws secretsmanager delete-secret \
  --secret-id "3t-app/backend-secret-key" \
  --force-delete-without-recovery \
  --region ap-south-1

# Then re-run terraform apply
terraform apply
```

### 2. Reconnect kubectl After Cluster Rebuild

```bash
# Remove stale context from kubeconfig (do this in Freelens or manually)
kubectl config delete-context <old-context-name>

# Pull new cluster config
aws eks update-kubeconfig --region ap-south-1 --name eks-cluster

# Rename the long ARN context
kubectl config rename-context \
  arn:aws:eks:ap-south-1:<account-id>:cluster/eks-cluster \
  eks

# Verify
kubectl config current-context
kubectl get nodes
```

### 3. Create the AWS Load Balancer Controller Folder

```bash
mkdir -p eks/services/aws-lb-controller
cd eks/services/aws-lb-controller
touch backend.tf providers.tf versions.tf variables.tf iam.tf helm.tf data.tf
```

### 4. `variables.tf`

```hcl
variable "eks_cluster_name" {
  default = "eks-cluster"
}

variable "vpc_name" {
  default = "eks-vpc"
}

variable "aws_region" {
  default = "ap-south-1"
}

variable "lb_controller_sa_name" {
  default = "aws-load-balancer-controller"
}
```

### 5. `data.tf` — Pull Cluster and VPC Data

```hcl
data "aws_vpc" "main" {
  filter {
    name   = "tag:Name"
    values = [var.vpc_name]
  }
}

data "aws_eks_cluster" "main" {
  name = var.eks_cluster_name
}

data "aws_eks_cluster_auth" "main" {
  name = var.eks_cluster_name
}

data "aws_iam_openid_connect_provider" "eks" {
  url = data.aws_eks_cluster.main.identity[0].oidc[0].issuer
}
```

### 6. `providers.tf`

```hcl
provider "aws" {
  region = var.aws_region
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.main.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.main.token
}

provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.main.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.main.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.main.token
  }
}
```

### 7. `iam.tf` — IRSA Setup

```hcl
# IAM Policy — permissions the controller needs to manage ALBs
resource "aws_iam_policy" "lb_controller" {
  name        = "AWSLoadBalancerControllerIAMPolicy"
  description = "Policy for AWS Load Balancer Controller"

  # Download the official policy from AWS docs:
  # https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json
  policy = file("${path.module}/lb_controller_iam_policy.json")
}

# IAM Role with OIDC trust
resource "aws_iam_role" "lb_controller" {
  name = "AmazonEKSLoadBalancerControllerRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = data.aws_iam_openid_connect_provider.eks.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(data.aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")}:sub" = "system:serviceaccount:kube-system:${var.lb_controller_sa_name}"
          "${replace(data.aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lb_controller" {
  policy_arn = aws_iam_policy.lb_controller.arn
  role       = aws_iam_role.lb_controller.name
}
```

### 8. Download the IAM Policy JSON

```bash
curl -o eks/services/aws-lb-controller/lb_controller_iam_policy.json \
  https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json
```

### 9. `helm.tf` — Install the Controller

```hcl
resource "helm_release" "lb_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  namespace  = "kube-system"
  version    = "1.8.1"

  set {
    name  = "clusterName"
    value = var.eks_cluster_name
  }

  set {
    name  = "serviceAccount.create"
    value = "true"
  }

  set {
    name  = "serviceAccount.name"
    value = var.lb_controller_sa_name
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.lb_controller.arn
  }

  set {
    name  = "region"
    value = var.aws_region
  }

  set {
    name  = "vpcId"
    value = data.aws_vpc.main.id
  }

  depends_on = [aws_iam_role_policy_attachment.lb_controller]
}
```

### 10. Deploy the Controller

```bash
cd eks/services/aws-lb-controller
terraform init
terraform apply
```

### 11. Verify the Controller Is Running

```bash
# Two pods should be running in kube-system
kubectl get pods -n kube-system | grep aws-load-balancer-controller

# Check the IngressClass was created
kubectl get ingressclass

# Should see: alb    ingress.k8s.aws/alb   <date>

# Verify the service account has the IRSA annotation
kubectl describe serviceaccount aws-load-balancer-controller -n kube-system | grep eks.amazonaws.com/role-arn
```

### 12. Create the Ingress Resource (`3t-app/k8s/ingress.yaml`)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: 3-tier-app-eks
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/healthcheck-path: /
    alb.ingress.kubernetes.io/healthcheck-port: "80"
spec:
  ingressClassName: alb
  rules:
  - host: yourdomain.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: backend
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 80
```

```bash
kubectl apply -f 3t-app/k8s/ingress.yaml

# Watch the ALB being provisioned (takes 2-3 minutes)
kubectl describe ingress app-ingress -n 3-tier-app-eks

# Get the ALB DNS name
kubectl get ingress app-ingress -n 3-tier-app-eks
```

### 13. Troubleshoot If ALB Does Not Provision

```bash
# Check controller logs — this is your primary debug tool
kubectl logs -n kube-system \
  -l app.kubernetes.io/name=aws-load-balancer-controller \
  --tail=50

# Common errors and fixes:
# "describe-security-groups denied" → IAM policy missing that permission, re-check policy JSON
# "context deadline exceeded" → re-apply the ingress, sometimes a transient issue
# "subnet not found" → subnet tags are missing, check kubernetes.io/role/elb tag on public subnets
# "cannot assume role" → OIDC issuer URL mismatch in trust policy, re-check the replace() in iam.tf
```

### 14. Database Migration Job (`3t-app/k8s/migration-job.yaml`)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
  namespace: 3-tier-app-eks
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migration
        image: livingdevopswithakhilesh/devopsdozo:backend-latest-1
        command: ["sh", "-c", "flask db upgrade"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secrets
              key: DATABASE_URL
  backoffLimit: 2
```

```bash
# Run migration before deploying backend
kubectl apply -f 3t-app/k8s/migration-job.yaml

# Wait for completion
kubectl wait --for=condition=complete job/db-migration -n 3-tier-app-eks --timeout=120s

# Only if migration succeeded, apply the backend
kubectl apply -f 3t-app/k8s/backend.yaml
kubectl apply -f 3t-app/k8s/frontend.yaml
```

---

**Next session:** Add HTTPS with ACM certificate, map a real domain in Route53 to the ALB, and move the Ingress into Terraform for full IaC coverage.

**Assignment:** The load balancer controller is now running but annotated with the IAM role. Try creating a second Ingress for a test service in a different namespace and annotate it with `alb.ingress.kubernetes.io/group.name: main-alb`. Verify in the AWS console that both Ingresses share the same ALB, not two separate ones.
