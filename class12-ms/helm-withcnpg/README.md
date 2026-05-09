# E-commerce Helm Chart (with CloudNativePG)

E-commerce microservices platform using **CloudNativePG** for production-grade PostgreSQL clusters with HA, automated failover, and backups.

## Why CloudNativePG?

| Feature | Standard PostgreSQL | CloudNativePG |
|---------|-------------------|---------------|
| High Availability | Manual setup | Built-in |
| Automated Failover | No | Yes |
| Backups | Manual | Automated |
| Point-in-Time Recovery | Manual | Built-in |
| Monitoring | Manual | Prometheus metrics |
| Rolling Updates | Downtime | Zero-downtime |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CloudNativePG Operator                   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ CNPG Cluster  │     │ CNPG Cluster  │     │ CNPG Cluster  │
│   products    │     │    users      │     │    orders     │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │  Primary  │ │     │ │  Primary  │ │     │ │  Primary  │ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │  Replica  │ │     │ │  Replica  │ │     │ │  Replica  │ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
└───────────────┘     └───────────────┘     └───────────────┘
```

## Prerequisites

- Kubernetes cluster (v1.24+)
- Helm 3.x
- kubectl configured
- **CloudNativePG Operator installed**

## Quick Start

### Step 1: Install CloudNativePG Operator

```bash
# Add the CloudNativePG Helm repository
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update

# Install the operator
helm install cnpg cnpg/cloudnative-pg \
  --namespace cnpg-system \
  --create-namespace \
  --wait

# Verify operator is running
kubectl get pods -n cnpg-system
```

### Step 2: Build Docker Images (if using local images)

```bash
# From project root
docker build -t product-service:local ./services/product-service
docker build -t user-service:local ./services/user-service
docker build -t cart-service:local ./services/cart-service
docker build -t order-service:local ./services/order-service
docker build -t payment-service:local ./services/payment-service
docker build -t notification-service:local ./services/notification-service
docker build -t frontend:local ./frontend
```

### Step 3: Deploy with Helm

```bash
# Basic installation
helm install ecommerce ./helm-withcnpg

# Install with custom namespace
helm install ecommerce ./helm-withcnpg --namespace ecommerce --create-namespace

# Install with custom values
helm install ecommerce ./helm-withcnpg -f my-values.yaml

# Dry run (preview what will be deployed)
helm install ecommerce ./helm-withcnpg --dry-run --debug
```

### Step 4: Wait for CNPG Clusters

```bash
# Watch cluster status
kubectl get clusters -n ecommerce -w

# Check all pods are running
kubectl get pods -n ecommerce

# Cluster should show "Cluster in healthy state"
kubectl describe cluster products-db -n ecommerce
```

### Step 5: Access the Application

```bash
# Frontend (NodePort)
# Access at: http://localhost:30000

# API Gateway (NodePort)
# Access at: http://localhost:30080
```

## Configuration

### CNPG-Specific Settings

```yaml
# values.yaml
cnpg:
  enabled: true
  image: ghcr.io/cloudnative-pg/postgresql:15.4
  instances: 3              # 1 primary + 2 replicas
  storage: 10Gi
  superuserPassword: postgres_superuser_123

  postgresql:
    max_connections: "200"
    shared_buffers: "256MB"
    effective_cache_size: "512MB"
    work_mem: "8MB"
    maintenance_work_mem: "128MB"

  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2000m
      memory: 2Gi

  monitoring:
    enablePodMonitor: true   # For Prometheus

  databases:
    - name: products
    - name: users
    - name: orders
    - name: payments
```

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `cnpg.enabled` | Enable CloudNativePG | `true` |
| `cnpg.instances` | PostgreSQL instances (1=standalone, 3=HA) | `1` |
| `cnpg.storage` | Storage per instance | `1Gi` |
| `cnpg.image` | PostgreSQL image | `ghcr.io/cloudnative-pg/postgresql:15.4` |
| `cnpg.postgresql.*` | PostgreSQL configuration | See values.yaml |
| `cnpg.monitoring.enablePodMonitor` | Enable Prometheus metrics | `false` |

## Production Configuration

### High Availability Setup

```yaml
# values-production.yaml
cnpg:
  instances: 3               # 1 primary + 2 replicas
  storage: 50Gi

  postgresql:
    max_connections: "500"
    shared_buffers: "1GB"
    effective_cache_size: "3GB"
    work_mem: "16MB"
    maintenance_work_mem: "256MB"

  resources:
    requests:
      cpu: 1000m
      memory: 2Gi
    limits:
      cpu: 4000m
      memory: 8Gi

  monitoring:
    enablePodMonitor: true
```

### Deploy to Production

```bash
helm install ecommerce-prod ./helm-withcnpg \
  --namespace ecommerce-prod \
  --create-namespace \
  -f values-production.yaml \
  --wait --timeout 10m
```

## CNPG Operations

### Check Cluster Status

```bash
# List all clusters
kubectl get clusters -n ecommerce

# Detailed cluster status
kubectl describe cluster products-db -n ecommerce

# Check which pod is primary
kubectl get pods -n ecommerce -l cnpg.io/cluster=products-db \
  -o custom-columns='NAME:.metadata.name,ROLE:.metadata.labels.role'
```

### Connect to Database

```bash
# Get superuser password
kubectl get secret products-db-superuser -n ecommerce \
  -o jsonpath='{.data.password}' | base64 -d

# Port forward to primary
kubectl port-forward svc/products-db-rw -n ecommerce 5432:5432

# Connect with psql
psql -h localhost -U postgres -d products
```

### Manual Failover

```bash
# Promote a replica to primary
kubectl cnpg promote products-db replica-pod-name -n ecommerce

# Or use annotation
kubectl annotate cluster products-db -n ecommerce \
  cnpg.io/requestedPrimarySwitch=replica-pod-name
```

### Backup and Restore

```bash
# Create on-demand backup (requires backup config)
kubectl apply -f - <<EOF
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata:
  name: products-db-backup-$(date +%Y%m%d)
  namespace: ecommerce
spec:
  cluster:
    name: products-db
EOF

# List backups
kubectl get backups -n ecommerce
```

### Monitoring with Prometheus

CNPG exposes metrics at `/metrics` endpoint:

```bash
# Check metrics endpoint
kubectl port-forward pod/products-db-1 -n ecommerce 9187:9187
curl localhost:9187/metrics
```

## Common Operations

### Upgrade

```bash
helm upgrade ecommerce ./helm-withcnpg -f my-values.yaml --wait
```

### Rollback

```bash
helm rollback ecommerce
```

### Uninstall

```bash
# Uninstall release (PVCs are retained by default)
helm uninstall ecommerce

# Delete PVCs if needed
kubectl delete pvc -n ecommerce -l cnpg.io/cluster

# Uninstall CNPG operator (if no longer needed)
helm uninstall cnpg -n cnpg-system
```

## Troubleshooting

### Cluster not becoming healthy

```bash
# Check operator logs
kubectl logs -n cnpg-system -l app.kubernetes.io/name=cloudnative-pg

# Check cluster events
kubectl describe cluster products-db -n ecommerce

# Check pod logs
kubectl logs products-db-1 -n ecommerce
```

### Connection refused

```bash
# Verify service exists
kubectl get svc -n ecommerce | grep products-db

# Services created by CNPG:
# - products-db-rw  (read-write, points to primary)
# - products-db-ro  (read-only, load balanced to replicas)
# - products-db-r   (any, load balanced to all)
```

### Storage issues

```bash
# Check PVC status
kubectl get pvc -n ecommerce

# Check storage class
kubectl get storageclass
```

## Chart Structure

```
helm-withcnpg/
├── Chart.yaml              # Chart metadata
├── values.yaml             # Default values
├── README.md               # This file
└── templates/
    ├── _helpers.tpl        # Template helpers
    ├── namespace.yaml      # Namespace
    ├── secrets.yaml        # Secrets
    ├── cnpg-clusters.yaml  # CloudNativePG Cluster CRDs
    ├── redis.yaml          # Redis deployment
    ├── rabbitmq.yaml       # RabbitMQ deployment
    ├── product-service.yaml
    ├── user-service.yaml
    ├── cart-service.yaml
    ├── order-service.yaml
    ├── payment-service.yaml
    ├── notification-service.yaml
    ├── api-gateway.yaml
    └── frontend.yaml
```

## Comparison: Which Chart to Use?

| Use Case | Recommended Chart |
|----------|-------------------|
| Local development | `helm/ecommerce` |
| CI/CD testing | `helm/ecommerce` |
| Staging environment | `helm-withcnpg` |
| Production | `helm-withcnpg` |
| Learning Kubernetes | `helm/ecommerce` |
| Learning CNPG | `helm-withcnpg` |
