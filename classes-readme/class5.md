Here's the README for this session:

---

# Week 3 - EKS Cluster Setup on AWS

## Topics Covered

**EKS Overview and Node Types**
- What EKS is and why managed Kubernetes exists — control plane complexity, DR, backup removed from your hands
- Three compute options in EKS: Fargate, Managed Node Groups, Self-Managed Nodes
- When to use each: Fargate for stateless workloads with no PV needs, Managed Node Groups for most teams, Self-Managed for strict compliance environments
- Real-world context: KPMG used Fargate + Self-Managed; startups typically use Managed Node Groups

**EKS Cluster Architecture Planning**
- IAM roles needed: one for the EKS cluster, one for worker nodes (ECR pull, EBS mount, etc.)
- Network planning: VPC CIDR sizing, private vs public subnets, IP address capacity per subnet
- How IPs are consumed: nodes, pods, services, add-on components (CSI, ALB controller, ArgoCD) all draw from the same pool
- VPC CNI plugin and its IP limits — sufficient for 99% of use cases; custom CNI plugins for Netflix-scale
- Cluster endpoint access modes: Public, Private, Public+Private — and whitelisting IPs via VPN

**Cluster Authentication**
- AWS credentials (access key/secret) vs Kubernetes cluster access — these are separate
- OIDC provider: how trust is established between AWS and the Kubernetes API server
- EKS Access Entry (new) vs ConfigMap-based auth (old `aws-auth`) — teams should move to Access Entry
- `aws eks update-kubeconfig` to populate `~/.kube/config`
- `kubectl config get-contexts`, `use-context`, `rename-context` for managing multiple clusters

**Add-ons**
- VPC CNI — required for nodes to register with EKS; without it nodes show NotReady
- kube-proxy — enables pod-to-pod communication across nodes
- CoreDNS — internal DNS for service discovery
- EBS CSI Driver — required for PersistentVolumes backed by EBS; needs IRSA (IAM Role for Service Account)
- Metrics Server — for HPA and `kubectl top`

**Fargate Profiles**
- How Fargate profiles work: namespace-to-profile mapping routes pods to serverless nodes
- Fargate requires private subnets only
- Docker Hub image pull restrictions on Fargate — use full image path

**Kubernetes Upgrades (Self-Managed)**
- Draining nodes before upgrade, cordon, PodDisruptionBudgets (PDB) — covered at high level
- Real upgrade automation: 800-line Python script on GitHub Actions cron, AWS + Kubernetes API calls
- AMI rotation every ~15 days per EKS version; user data for custom patching via SSM documents
- Race condition issue with SSM documents blocking EFS volume mounts — automated node termination as fix

**Karpenter vs Cluster Autoscaler**
- Cluster Autoscaler is older; Karpenter is the recommended replacement
- EKS Auto Mode ships with Karpenter by default
- Karpenter supports node pools, right-sizing, automatic AMI rotation — covered in a dedicated session later

---

## Exercise — Step by Step

### 1. Create the EKS IAM Role (Console)

1. Go to IAM → Roles → Create Role
2. Trusted entity: EKS → EKS Cluster
3. Attach policy: `AmazonEKSClusterPolicy`
4. Name the role (e.g. `eks-cluster-role-march26`)

### 2. Create the Node IAM Role (Console)

1. Go to IAM → Roles → Create Role
2. Trusted entity: AWS Service → EC2
3. Attach policies:
   - `AmazonEKSWorkerNodePolicy`
   - `AmazonEKS_CNI_Policy`
   - `AmazonEC2ContainerRegistryReadOnly`
4. Name the role (e.g. `eks-node-role-march26`)

### 3. Create the EKS Cluster (Console)

1. Go to EKS → Create Cluster → Custom Configuration
2. Name: `demo`
3. Kubernetes version: `1.32` (avoid latest in production)
4. Cluster IAM Role: select the role created in step 1
5. Cluster access:
   - Bootstrap cluster admin access: **Enabled**
   - Authentication mode: **EKS API** (not ConfigMap)
6. Networking:
   - VPC: Default VPC (for demo)
   - Subnets: select all default subnets
   - Security Group: select any existing one
   - Cluster endpoint access: **Public and Private**
7. Logging: skip for cost (in production enable API + Audit)
8. Add-ons: keep `kube-proxy` and `metrics-server`; **do not** add VPC CNI yet (intentional — to see nodes go NotReady)
9. Review and Create (takes ~10 minutes)

### 4. Configure kubectl to Talk to the Cluster

```bash
# Update kubeconfig
aws eks update-kubeconfig --region ap-south-1 --name demo

# Verify current context
kubectl config current-context

# List all contexts
kubectl config get-contexts

# Rename the long ARN context to something short
kubectl config rename-context <long-arn-context> demo

# Switch context
kubectl config use-context demo

# Verify (will fail auth until access entry is configured)
kubectl get nodes
```

### 5. Add EKS Access Entry for CLI User

1. In EKS console → Cluster → Access tab
2. Create access entry
3. Principal ARN: your IAM user ARN (e.g. `arn:aws:iam::ACCOUNT_ID:user/cli-user`)
4. Access scope: **Cluster**
5. Policy: `AmazonEKSAdminPolicy` or `AmazonEKSViewPolicy` (as needed)
6. Run `kubectl get nodes` again — should now return (no nodes yet)

### 6. Create a Managed Node Group

1. EKS → Cluster → Compute → Add Node Group
2. Name: `demo-nodes`
3. Node IAM Role: select the role created in step 2
4. AMI type: `AL2023_x86_64_STANDARD` (default)
5. Instance type: `t3.medium` (or smaller for cost)
6. Scaling:
   - Min: 1
   - Desired: 2
   - Max: 3
7. Subnets: select default subnets (public for this demo; use private in production)
8. Create

> After creation, go to EC2 — you will see 2 instances. But `kubectl get nodes` will show `NotReady` because VPC CNI is missing.

### 7. Install the VPC CNI Add-on

1. EKS → Cluster → Add-ons → Get more add-ons
2. Find and select **Amazon VPC CNI**
3. Keep defaults, no IAM role needed for basic use
4. Create

> Wait ~1 minute. Nodes will move from `NotReady` to `Ready`.

```bash
kubectl get nodes
# Both nodes should now show Ready

kubectl get pods -A
# You will see kube-proxy, coredns, metrics-server pods running
```

### 8. Deploy a Test Workload on Managed Nodes

```bash
# Apply a deployment (nginx or your existing 3-tier app manifest)
kubectl apply -f deployment.yaml

# Check pod placement
kubectl get pods -o wide
# Note which node IPs the pods are scheduled on
```

### 9. Create a Fargate Profile

> You need a private subnet first. Default VPC only has public subnets.

**Create a private subnet (quick demo workaround):**
1. VPC → Subnets → Create Subnet
2. Choose Default VPC
3. CIDR: pick a non-overlapping range (e.g. `10.0.56.0/24`)
4. Create a Route Table (no internet gateway route) and associate this subnet with it — this makes it effectively private

**Create the Fargate Profile:**
1. EKS → Cluster → Compute → Add Fargate Profile
2. Name: `week-three` (same as target namespace)
3. Pod execution role: use default Fargate role
4. Subnets: select the private subnet created above
5. Namespace selector: `week-three`
6. Create

### 10. Deploy Workload to Fargate

```yaml
# deployment with namespace
apiVersion: v1
kind: Namespace
metadata:
  name: week-three
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: week-three
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: public.ecr.aws/nginx/nginx:latest   # use full path on Fargate
        ports:
        - containerPort: 80
```

```bash
kubectl apply -f fargate-deployment.yaml

# Watch pods spin up (takes ~60 seconds on Fargate)
kubectl get pods -n week-three -w

# Confirm they are NOT on your EC2 managed nodes
kubectl get pods -n week-three -o wide
```

### 11. Cleanup (to avoid costs)

```bash
# Delete node group first (wait for EC2 instances to terminate)
# Then delete the cluster from console
# Do NOT delete cluster before nodes are gone
```

---

**Terraform equivalent** of the full setup is in `eks/eks-infra/` — covered in the next session.
