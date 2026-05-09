# Week 5 - 3-Tier App Deployment on EKS

## Topics Covered

**Architecture Planning for 3-Tier App on EKS**
- App components: React frontend, Flask backend, PostgreSQL on RDS
- Frontend talks to backend via internal ClusterIP service — never directly to database
- Backend talks to RDS via private endpoint — both must be in the same VPC
- Database in dedicated subnets, separate from application subnets — standard practice in every company
- External service pattern: creating a Kubernetes service that points to an outside endpoint (RDS) so pods reference it by service name, not raw endpoint

**RDS Provisioning with Terraform**
- Random password generation using `random` provider — never hardcode DB passwords
- Storing DB credentials in AWS Secrets Manager immediately after creation
- DB subnet group requires dedicated subnets — plan your CIDR blocks so you have room for a third set (application subnets, database subnets, public subnets)
- Data source to pull VPC ID from another repo's state — `aws_vpc` data source with filter by name
- Common mistake: wrong VPC ID causes DB to land in a different VPC from your EKS nodes — check endpoint VPC after creation

**Secrets and ConfigMaps — What Goes Where**
- ConfigMap: non-sensitive config — `FLASK_DEBUG`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `ALLOWED_ORIGINS`
- Secret (opaque type): sensitive data — `DATABASE_URL`, `SECRET_KEY`, DB username/password
- Kubernetes secret types: `Opaque` (key-value pairs), `kubernetes.io/basic-auth` (username+password), `kubernetes.io/dockerconfigjson` (image pull), TLS
- Using `valueFrom.configMapKeyRef` and `valueFrom.secretKeyRef` in deployment env blocks — never hardcode values inline
- Why Terraform for secrets: database endpoint is only known after RDS is created — Terraform can chain creation → output → secret injection dynamically without ever writing credentials to a file

**Init Containers**
- Pattern: init container runs a job and exits before the main container starts
- Use case here: `busybox` running `nslookup` against the RDS DNS endpoint — confirms DB is reachable before Flask starts
- Why not use init container for DB migrations: with 20+ pod replicas all trying to create the same tables simultaneously, you risk race conditions and data corruption
- Correct migration pattern: run as a standalone Kubernetes `Job` in the CI/CD pipeline before the Deployment rollout; fail the pipeline if the Job fails
- Sidecar container pattern (mentioned for context): always-running second container in the same pod — used for log shipping, service mesh proxies (Envoy), metrics scraping

**CORS — Why It Matters for Deployments**
- `ALLOWED_ORIGINS` tells the Flask backend which frontend origins to accept requests from
- Without this, browsers block cross-origin requests from frontend to backend
- In production: set to your actual domain (`https://yourdomain.com`); in local Docker Compose: `http://localhost:80`
- This is a config value, not a networking rule — it lives in ConfigMap

**ECR Image Pull Without imagePullSecrets**
- EKS managed node groups have an IAM role with `AmazonEC2ContainerRegistryReadOnly` attached
- This means pods can pull from ECR without any `imagePullSecret` in the deployment spec
- The IAM role on the node handles authentication transparently via instance metadata
- This is one of the EKS ecosystem advantages — no token management for image pulls

**Ingress and AWS Load Balancer Controller**
- Why not use `type: LoadBalancer` on every service: each service gets its own ALB — 25 microservices = 25 load balancers = excessive cost and management overhead
- Correct pattern: one ALB, all traffic enters through it, routing rules send requests to the right service based on path or hostname
- Ingress resource: the Kubernetes object that defines these routing rules — `/account` → account-service, `/feed` → feed-service, etc.
- AWS Load Balancer Controller: a Helm-installed controller running inside the cluster that watches Ingress objects and creates/updates ALBs in AWS
- SSL termination: two approaches — (1) inside cluster via cert-manager + Let's Encrypt (Akhilesh's old approach, nginx-based), (2) at ALB level via ACM certificate (current approach after nginx controller deprecation)
- ALB (layer 7) vs NLB (layer 4): SSL termination only works at ALB; NLB does not decrypt HTTPS

**IRSA — IAM Roles for Service Accounts**
- Problem: the Load Balancer Controller pod needs AWS IAM permissions to create ALBs, but pods don't automatically have AWS credentials
- Solution: create an IAM role with the right permissions + a trust policy that allows the OIDC provider of your cluster to assume it
- OIDC provider: every EKS cluster has one; you must register it in IAM Identity Providers — the Terraform EKS module does this automatically
- Trust relationship: `StringEquals` condition on `<oidc-provider>:sub` = `system:serviceaccount:kube-system:aws-load-balancer-controller`
- Service account in Kubernetes gets annotated with the IAM role ARN — this links both sides
- Pod Identity is the newer alternative — covers in a later session

**DNS Service Discovery Inside the Cluster**
- Every Kubernetes Service gets a DNS name: `<service-name>.<namespace>.svc.cluster.local`
- Using just `service-name:port` works only within the same namespace
- Across namespaces: use the full DNS name — frontend can reach backend in a different namespace this way
- Best practice: always use full DNS names in environment variables so configs work across namespace boundaries

**Ingress vs Gateway API**
- Gateway API is the newer standard; Ingress is the older one
- AWS Load Balancer Controller implements both
- Migrating from nginx ingress to ALB: change the `ingressClassName`, switch load balancer type from NLB to ALB, map ACM certificate ARN in annotations — roughly 5 changes, 5 minutes if tested first
- In production: test in staging first, take a small downtime window, or blue/green with a second cluster if zero downtime is required

**ALB Limitations**
- Maximum ~200 routing rules per ALB — covers 99% of use cases
- For 500+ rules (rare, very large-scale apps): consider custom solutions like Kong, Traefik, or AWS API Gateway
- Rule: try the simple AWS-native solution first; go to complex solutions only when you hit actual limits

---

## Exercise — Step by Step

### 1. Add Database Subnets to Your VPC

Edit `eks/eks-infra/network.tf` — add a third subnet block for the database tier:

```hcl
# Add to your existing VPC module
database_subnets = ["10.0.4.0/24", "10.0.5.0/24", "10.0.6.0/24"]
create_database_subnet_group = true
```

> Make sure these CIDRs do not overlap with your existing private (`10.0.1-3.0/24`) or public (`10.0.101-103.0/24`) subnets.

### 2. Create the App Terraform Folder Structure

```bash
mkdir -p 3t-app/infra
mkdir -p 3t-app/k8s
```

### 3. Create `3t-app/infra/backend.tf`

```hcl
terraform {
  backend "s3" {
    bucket       = "state-bucket-<account-id>"
    key          = "k8sbootcamp/3t-app/infra/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

### 4. Create `3t-app/infra/providers.tf`

```hcl
terraform {
  required_version = "1.12.1"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1"
  default_tags {
    tags = {
      Terraform   = "true"
      Application = "3t-app"
    }
  }
}
```

### 5. Create `3t-app/infra/data.tf` — Pull VPC from EKS Repo

```hcl
variable "vpc_name" {
  default = "eks-vpc"
}

variable "eks_cluster_name" {
  default = "eks-cluster"
}

data "aws_vpc" "eks" {
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

provider "kubernetes" {
  host                   = data.aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.main.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.main.token
}
```

> This repo must be applied **after** the EKS cluster exists. The Kubernetes provider authenticates at plan time.

### 6. Create `3t-app/infra/rds.tf`

```hcl
resource "random_password" "db" {
  length  = 16
  special = false
}

resource "aws_db_subnet_group" "app" {
  name       = "3t-app-db-subnet-group"
  subnet_ids = data.aws_subnets.database.ids
}

data "aws_subnets" "database" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.eks.id]
  }
  filter {
    name   = "tag:Name"
    values = ["*database*"]
  }
}

resource "aws_security_group" "rds" {
  name   = "3t-app-rds-sg"
  vpc_id = data.aws_vpc.eks.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.eks.cidr_block]
  }
}

resource "aws_db_instance" "app" {
  identifier        = "3t-app-postgres"
  engine            = "postgres"
  engine_version    = "15.10"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  db_name  = "appdb"
  username = "postgres"
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.app.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  skip_final_snapshot = true
  publicly_accessible = false
}

resource "aws_secretsmanager_secret" "db_creds" {
  name = "3t-app/db-credentials"
}

resource "aws_secretsmanager_secret_version" "db_creds" {
  secret_id = aws_secretsmanager_secret.db_creds.id
  secret_string = jsonencode({
    DATABASE_URL = "postgresql://postgres:${random_password.db.result}@${aws_db_instance.app.address}:5432/appdb"
    username     = "postgres"
    password     = random_password.db.result
  })
}
```

### 7. Create `3t-app/infra/k8s_config.tf` — Namespace, ConfigMap, Secret

```hcl
resource "kubernetes_namespace" "app" {
  metadata {
    name = "3-tier-app-eks"
  }
}

resource "kubernetes_config_map" "backend" {
  metadata {
    name      = "backend-config"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    FLASK_DEBUG      = "false"
    DB_HOST          = aws_db_instance.app.address
    DB_PORT          = "5432"
    DB_NAME          = "appdb"
    ALLOWED_ORIGINS  = "https://yourdomain.com"
  }
}

resource "kubernetes_secret" "backend" {
  metadata {
    name      = "db-secrets"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  type = "Opaque"

  data = {
    DATABASE_URL = "postgresql://postgres:${random_password.db.result}@${aws_db_instance.app.address}:5432/appdb"
    SECRET_KEY   = random_password.secret_key.result
    DB_USERNAME  = "postgres"
    DB_PASSWORD  = random_password.db.result
  }
}

resource "random_password" "secret_key" {
  length  = 16
  special = true
}

resource "kubernetes_config_map" "frontend" {
  metadata {
    name      = "frontend-config"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    BACKEND_URL = "http://backend.3-tier-app-eks.svc.cluster.local:8000"
  }
}
```

### 8. Apply the App Infra

```bash
cd 3t-app/infra
terraform init
terraform apply
```

### 9. Create Backend Deployment Manifest (`3t-app/k8s/backend.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: 3-tier-app-eks
spec:
  replicas: 1       # Keep 1 while testing migration
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      initContainers:
      - name: wait-for-db
        image: busybox
        command: ['sh', '-c', 'until nslookup $(DB_HOST); do echo waiting for database; sleep 2; done']
        env:
        - name: DB_HOST
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: DB_HOST
      containers:
      - name: backend
        image: livingdevopswithakhilesh/devopsdozo:backend-latest-1
        imagePullPolicy: Always
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secrets
              key: DATABASE_URL
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: db-secrets
              key: SECRET_KEY
        - name: FLASK_DEBUG
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: FLASK_DEBUG
        - name: ALLOWED_ORIGINS
          valueFrom:
            configMapKeyRef:
              name: backend-config
              key: ALLOWED_ORIGINS
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: 3-tier-app-eks
spec:
  selector:
    app: backend
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

### 10. Create Frontend Deployment Manifest (`3t-app/k8s/frontend.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: 3-tier-app-eks
spec:
  replicas: 2
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
      - name: frontend
        image: livingdevopswithakhilesh/devopsdozo:frontend-latest-1
        imagePullPolicy: Always
        ports:
        - containerPort: 80
        env:
        - name: BACKEND_URL
          valueFrom:
            configMapKeyRef:
              name: frontend-config
              key: BACKEND_URL
        readinessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 15
          periodSeconds: 20
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: 3-tier-app-eks
spec:
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
```

### 11. Apply Manifests and Test with Port Forward

```bash
kubectl apply -f 3t-app/k8s/backend.yaml
kubectl apply -f 3t-app/k8s/frontend.yaml

# Watch pods come up
kubectl get pods -n 3-tier-app-eks -w

# Check init container logs if backend is stuck
kubectl logs -n 3-tier-app-eks <backend-pod> -c wait-for-db

# Test frontend locally via port forwarding
kubectl port-forward -n 3-tier-app-eks svc/frontend 8080:80

# Open http://localhost:8080 in browser
```

### 12. Troubleshoot DB Connectivity

If backend logs show connection errors:

```bash
# Check backend logs
kubectl logs -n 3-tier-app-eks deployment/backend

# Verify the secret has the right values
kubectl get secret db-secrets -n 3-tier-app-eks -o jsonpath='{.data.DATABASE_URL}' | base64 -d

# Verify RDS is in the same VPC as your EKS nodes
# Go to RDS → your instance → Connectivity → VPC
# Must match the VPC shown in EC2 → your EKS nodes

# Verify RDS security group allows port 5432 from the VPC CIDR
```

---

**Assignment:** The DB password is already in Secrets Manager. Try removing the `kubernetes_secret` Terraform resource and instead write an init container that fetches the secret directly from Secrets Manager using the AWS CLI, writes it to a shared `emptyDir` volume, and has the main container read from that file. This is closer to how production secret injection works.
