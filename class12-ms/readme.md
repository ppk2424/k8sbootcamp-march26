# E-Commerce Microservices Platform

## Path to the apps
```
../microservices-k8s-ecommerce/
```

## Create Kind Cluster
```bash
kind create cluster --config kind-config.yaml --name ecom-ms
```

---

## Microservices Overview

| Service | Language | Database | Port | Purpose |
|---------|----------|----------|------|---------|
| Product Service | Go | PostgreSQL (products) | 8001 | Product catalog management |
| User Service | Node.js | PostgreSQL (users) | 8002 | User authentication & profiles |
| Cart Service | Node.js | Redis | 8003 | Session/cart state management |
| Order Service | Go | PostgreSQL (orders) | 8004 | Order processing & tracking |
| Payment Service | Python/Flask | PostgreSQL (payments) | 8005 | Payment processing (Razorpay) |
| Notification Service | Python/Flask | None (RabbitMQ + SES) | 8006 | Email notifications |

---

## Database Configuration with CNPG (CloudNativePG)

### CNPG Cluster Setup

Each PostgreSQL database runs as a CNPG cluster with:
- **Image**: `ghcr.io/cloudnative-pg/postgresql:15.4`
- **Instances**: 1 (dev) / 3 (prod: 1 primary + 2 replicas)
- **Storage**: 1Gi per cluster

### CNPG Service Endpoints

For each database, CNPG automatically creates:
- `{db-name}-rw` - Read-write endpoint (connects to primary)
- `{db-name}-ro` - Read-only endpoint (load balanced to replicas)
- `{db-name}-r` - All instances endpoint

---

## Secrets Configuration

### 1. Database Secrets (Per CNPG Cluster)

**Superuser Secret** (`{db-name}-superuser`):
```yaml
username: postgres
password: postgres_superuser_123
```

**Application User Secret** (`{db-name}-app`):
```yaml
username: ecommerce_user
password: secure_password_123
dbname: {database-name}
host: {db-name}-rw
port: "5432"
```

### 2. Common Secrets

| Secret Name | Keys |
|-------------|------|
| `db-credentials` | `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| `redis-credentials` | `REDIS_PASSWORD` |
| `rabbitmq-credentials` | `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS` |
| `app-secrets` | `JWT_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` |

---

## Service Database Connections

### Product Service (Go)

| Variable | Value |
|----------|-------|
| `PRODUCT_DB_HOST` | `products-rw` (CNPG) / `postgres-products` (standard) |
| `PRODUCT_DB_PORT` | `5432` |
| `PRODUCT_DB_USER` | `ecommerce_user` (from `db-credentials`) |
| `PRODUCT_DB_PASSWORD` | `secure_password_123` (from `db-credentials`) |
| `PRODUCT_DB_NAME` | `products` |

---

### User Service (Node.js)

| Variable | Value |
|----------|-------|
| `USER_DB_HOST` | `users-rw` (CNPG) / `postgres-users` (standard) |
| `USER_DB_PORT` | `5432` |
| `USER_DB_USER` | `ecommerce_user` (from `db-credentials`) |
| `USER_DB_PASSWORD` | `secure_password_123` (from `db-credentials`) |
| `USER_DB_NAME` | `users` |
| `JWT_SECRET` | from `app-secrets` secret |

---

### Cart Service (Node.js)

**Note**: Cart Service uses Redis, not PostgreSQL.

| Variable | Value |
|----------|-------|
| `REDIS_HOST` | `redis` |
| `REDIS_PORT` | `6379` |
| `REDIS_PASSWORD` | `redis_password_123` (from `redis-credentials`) |
| `REDIS_DB` | `0` |
| `JWT_SECRET` | from `app-secrets` secret |

---

### Order Service (Go)

| Variable | Value |
|----------|-------|
| `ORDER_DB_HOST` | `orders-rw` (CNPG) / `postgres-orders` (standard) |
| `ORDER_DB_PORT` | `5432` |
| `ORDER_DB_USER` | `ecommerce_user` (from `db-credentials`) |
| `ORDER_DB_PASSWORD` | `secure_password_123` (from `db-credentials`) |
| `ORDER_DB_NAME` | `orders` |
| `RABBITMQ_HOST` | `rabbitmq` |
| `RABBITMQ_PORT` | `5672` |
| `RABBITMQ_USER` | `rabbitmq` (from `rabbitmq-credentials`) |
| `RABBITMQ_PASSWORD` | `secure_rabbitmq_password` (from `rabbitmq-credentials`) |
| `JWT_SECRET` | from `app-secrets` secret |

---

### Payment Service (Python/Flask)

| Variable | Value |
|----------|-------|
| `PAYMENT_DB_HOST` | `payments-rw` (CNPG) / `postgres-payments` (standard) |
| `PAYMENT_DB_PORT` | `5432` |
| `PAYMENT_DB_USER` | `ecommerce_user` (from `db-credentials`) |
| `PAYMENT_DB_PASSWORD` | `secure_password_123` (from `db-credentials`) |
| `PAYMENT_DB_NAME` | `payments` |
| `RAZORPAY_KEY_ID` | from `app-secrets` secret |
| `RAZORPAY_KEY_SECRET` | from `app-secrets` secret |
| `RAZORPAY_WEBHOOK_SECRET` | from `app-secrets` secret |
| `JWT_SECRET` | from `app-secrets` secret |

---

### Notification Service (Python/Flask)

**Note**: Notification Service has no database, uses RabbitMQ + AWS SES.

| Variable | Value |
|----------|-------|
| `RABBITMQ_HOST` | `rabbitmq` |
| `RABBITMQ_PORT` | `5672` |
| `RABBITMQ_USER` | `rabbitmq` (from `rabbitmq-credentials`) |
| `RABBITMQ_PASSWORD` | `secure_rabbitmq_password` (from `rabbitmq-credentials`) |
| `AWS_ACCESS_KEY_ID` | placeholder |
| `AWS_SECRET_ACCESS_KEY` | placeholder |
| `AWS_REGION` | `us-east-1` |
| `SES_SENDER_EMAIL` | `noreply@example.com` |

---

## Deployment Options

### Option 1: Standard Helm Chart (StatefulSets)
```bash
helm install ecommerce ./helm/ecommerce -n ecommerce --create-namespace
```
- Uses standalone PostgreSQL StatefulSets
- 4 separate databases: `postgres-products`, `postgres-users`, `postgres-orders`, `postgres-payments`

### Option 2: CNPG Helm Chart (Production HA)
```bash
# Install CNPG operator first
kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.22/releases/cnpg-1.22.0.yaml

# Deploy application
helm install ecommerce ./helm-withcnpg -n ecommerce --create-namespace
```
- Uses CloudNativePG operator
- Automatic HA with failover
- Built-in backup/restore with WAL archiving
- Point-in-Time Recovery (PITR) support

---

## CNPG vs Standard Comparison

| Aspect | CNPG | Standard StatefulSet |
|--------|------|---------------------|
| Host Pattern | `{db-name}-rw` | `postgres-{db-name}` |
| High Availability | Automatic | Manual |
| Failover | Automatic | Manual |
| Backup | Built-in WAL archiving | Manual |
| PITR | Supported | Not available |
| Monitoring | Prometheus metrics | None |

---

## Key Configuration Files

| File | Purpose |
|------|---------|
| `helm-withcnpg/templates/cnpg-clusters.yaml` | CNPG cluster definitions |
| `helm-withcnpg/templates/secrets.yaml` | All secrets |
| `helm-withcnpg/values.yaml` | Configuration values |
| `helm/ecommerce/templates/postgres.yaml` | Standard PostgreSQL StatefulSets |
| `setup-cnpg/cluster.yaml` | Standalone CNPG cluster example |

---

## Production Best Practices

1. Use `-rw` endpoint for writes, `-ro` for read-heavy queries
2. Minimum 3 instances for production HA
3. Enable WAL archiving for PITR
4. Use strong passwords (20+ characters)
5. Pin PostgreSQL version (never use `:latest`)
6. Test restores regularly
