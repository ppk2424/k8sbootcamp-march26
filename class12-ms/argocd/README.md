# ArgoCD Deployment for Ecommerce Application

This directory contains ArgoCD manifests to deploy the ecommerce helm chart using two approaches.

## Prerequisites

1. A running Kubernetes cluster
2. ArgoCD installed in the cluster

### Install ArgoCD (if not already installed)

```bash
# Create namespace
kubectl create namespace argocd

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for ArgoCD to be ready
kubectl wait --for=condition=available --timeout=300s deployment/argocd-server -n argocd

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

### Access ArgoCD UI

```bash
# Port forward to access UI
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Access at: https://localhost:8080
# Username: admin
# Password: (from the command above)
```

## Deployment Options

### Option 1: Normal Way (Direct Application)

This approach uses a single Application manifest that directly deploys the helm chart.

```bash
kubectl apply -f ecommerce-app.yaml
```

**Use this when:**
- You have a single application to deploy
- Simple setup with minimal management overhead

### Option 2: App of Apps Pattern

This approach uses a parent Application that manages child Applications.

```bash
kubectl apply -f app-of-apps.yaml
```

**Use this when:**
- You have multiple applications to deploy
- You want centralized management of all apps
- Adding new apps should be as simple as adding a YAML file

**To add more applications:**
1. Create a new Application manifest in the `apps/` directory
2. Commit and push to the repository
3. The parent app will automatically sync and deploy the new app

## Directory Structure

```
argocd/
├── README.md               # This file
├── ecommerce-app.yaml      # Normal way - direct Application
├── app-of-apps.yaml        # App of Apps - parent Application
└── apps/
    └── ecommerce.yaml      # Child app for App of Apps pattern
```

## Verify Deployment

```bash
# Check ArgoCD applications
kubectl get applications -n argocd

# Check application sync status
kubectl describe application ecommerce -n argocd

# Check deployed resources
kubectl get all -n ecommerce
```

## Cleanup

```bash
# Delete using normal way
kubectl delete -f ecommerce-app.yaml

# Or delete using app of apps
kubectl delete -f app-of-apps.yaml
```
