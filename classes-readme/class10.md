# Class Notes — April 26, 2026
## LivingDevOps Bootcamp · Session 10

---

## Topics Covered

### 1. E-Commerce Microservices Architecture

Introduced a realistic production-grade e-commerce app built for teaching purposes. The architecture mirrors how large-scale platforms are structured:

- **Frontend** — React + Vite
- **API Gateway** — Nginx (handles routing, CORS, authentication proxy)
- **Microservices** — Product (Go), User (Node.js), Cart (Node.js), Order (Go), Payment (Python), Notification (Python)
- **Databases** — 4 separate PostgreSQL instances (one per service)
- **Cache** — Redis (used by Cart Service, TTL-based)
- **Message Queue** — RabbitMQ (used for async order events)
- **Monitoring** — Prometheus + Grafana

---

### 2. Why Separate Databases per Service

Each microservice owns its own database — this is the **database-per-service pattern**. Key reasons:

- Prevents tight coupling between services
- Enables independent scaling
- Avoids contention on a single database under heavy load

---

### 3. Message Queues and Why We Need Them

When millions of users trigger actions simultaneously (likes, orders, notifications), a direct database write for each request causes failures. A queue absorbs the burst:

- Producer pushes messages to the queue
- Consumer processes them at its own pace
- Examples: **Kafka** (LinkedIn), **RabbitMQ**, **AWS SQS**
- The Notification Service consumes `order.created` events from RabbitMQ and sends emails via AWS SES

---

### 4. Rate Limiting vs. Queue-Based Scaling

These solve different problems:

| Concept | Purpose |
|---|---|
| Rate Limiting | Prevent abuse from a single user or bot |
| Message Queue | Handle massive legitimate traffic without overwhelming the database |

Rate limiting is per-user; queues are for system-level scale.

---

### 5. API Gateway vs. Ingress Controller

A common point of confusion:

- **Ingress Controller** (Nginx Ingress) — handles **user-to-application** traffic. Routes external HTTP requests to the right frontend/backend based on domain or path.
- **API Gateway** (Nginx configured as a gateway) — handles **API-to-API** (service-to-service) communication inside the cluster. Manages routing, authentication, and CORS between backend services.

The API Gateway is not user-facing. It is an internal routing and authentication layer between microservices.

---

### 6. Deployments vs. StatefulSets

| Resource | Use For | Key Property |
|---|---|---|
| Deployment | Stateless services (APIs, frontend, Redis cache) | Pods are interchangeable, random names |
| StatefulSet | Stateful services (PostgreSQL, RabbitMQ) | Pods get stable names (`postgres-0`, `postgres-1`), individual PVCs |

Why databases cannot use Deployments:

- A Deployment may attach the same PVC to multiple pods — data corruption risk
- Pod names are random; a dead pod comes back with a different name, breaking database connection strings
- StatefulSets guarantee: same name on restart, dedicated storage per pod, ordered startup

---

### 7. Headless Services

Used with StatefulSets so applications can address individual pods by a stable DNS name:

```
postgres-products-0.postgres-products.ecommerce.svc.cluster.local
```

With a normal ClusterIP service, traffic is load-balanced — acceptable for stateless APIs, but not for databases where you must distinguish writer from reader.

---

### 8. Kind (Kubernetes in Docker)

Replaced Minikube for local development in this bootcamp:

- Supports **multi-node clusters** on a single machine
- Can run **multiple clusters simultaneously** (useful for dev/staging simulation)
- Works on Mac, Linux, and Windows (via Chocolatey)
- Port mapping in the config file exposes NodePorts to localhost for browser access

---

### 9. Docker Compose as a Reference Tool

Docker Compose is not used to run workloads in Kubernetes — it is used by developers to run the full stack locally and by DevOps engineers to **understand the application**:

- What services exist and what ports they use
- Which services need volumes (stateful)
- Which environment variables and secrets are required
- Startup dependencies (`depends_on`)

Reading the Compose file is step one before writing Kubernetes manifests.

---

### 10. CloudNativePG

The production-recommended way to run PostgreSQL on Kubernetes:

- Open-source operator with 8.5K+ GitHub stars
- Manages writer/reader clusters, failover, and replication
- Used by companies like Netflix, Flipkart, and others running Postgres on Kubernetes
- To be covered in the CRD/Operator sessions

---

### 11. Custom Resource Definitions (CRDs) and Operators — Introduction

When Helm charts alone are not enough (complex stateful setups with ordering, restart logic, and dependency management), teams use CRDs + Operators:

- **CRD** — extends the Kubernetes API with a custom resource type
- **Operator** — a controller that watches CRDs and acts on them (reconciliation/control loop)
- ArgoCD, Prometheus, CloudNativePG are all deployed as CRDs with operators
- Can be written in **Python** (kopf) or Go; Python is sufficient for most use cases
- Full implementation will be covered in upcoming sessions

---

## Key Discussion Points

- `clusterIP: None` in a Service spec = **Headless Service**
- StatefulSet pods start in order; the second pod will not start until the first is `Running`
- Redis is deployed as a Deployment (cache data is ephemeral by design; can be upgraded to StatefulSet for persistence)
- Postman is the recommended tool for testing service-to-service API calls locally
- For Kafka vs. RabbitMQ: understand the concept and the use case; learn the specific tool when you interview for a company that uses it
- Python is increasingly required in DevOps roles — learn it, use it, do not skip it
- You do not need to learn Go to write operators; Python (kopf) is fully supported

---

## Exercise / Homework

1. **Clone the repo** — Akhilesh will push the e-commerce microservices app to GitHub. Fork it to your own account.

2. **Read the codebase** — Go through `docker-compose.yml`, `ARCHITECTURE.md`, and `SERVICE_CONNECTIONS.md`. Use Claude or ChatGPT to help understand anything unclear.

3. **Answer these questions for each service:**
   - Is it stateful or stateless?
   - What environment variables does it need?
   - What secrets does it require?
   - Which services does it depend on?

4. **Set up Kind** on your local machine:
   - Install Kind (Mac: `brew install kind`, Windows: `choco install kind`)
   - Create a multi-node cluster using the config shown in class
   - Verify with `kubectl get nodes`

5. **Research:** Spend 30 minutes on YouTube or docs on the difference between API Gateway and Ingress Controller. Come prepared to explain it in your own words next class.

6. **Optional challenge:** Write a headless service manifest for `postgres-products` and explain why `clusterIP: None` is required.

---

## What's Next

- Deploying the full e-commerce app on Kind step by step
- StatefulSet deep-dive with CloudNativePG
- CRDs and Operators — building simple custom controllers
- Then moving everything to EKS

---

*Next class: check the bootcamp calendar. Recordings are available in the shared Google Drive folder.*
