# Monitoring & Observability Guide

How metrics, logs, alerts, and dashboards work for the ecommerce platform on EKS.

This stack follows a **two-layer model**:

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Cluster** | `eks/k8s-services/logging-monitoring/` | Install Prometheus, Grafana, Loki, Promtail, exporters |
| **App** | `eks-microservice-implementation/infra/observability/` | Wire microservices into that stack (scrape, rules, dashboards) |

Think of the cluster layer as the **grid**; the app layer connects your **appliances**.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ecommerce namespace                                                    │
│                                                                         │
│  Microservices (Go / Node / Python)                                     │
│    • GET /metrics  ──────────────────────────────┐                      │
│    • stdout logs  ───────────┐                   │                      │
│                              │                   │                      │
│  Redis, RabbitMQ, CNPG Postgres                │                      │
└──────────────────────────────│───────────────────│──────────────────────┘
                               │                   │
                               ▼                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  monitoring namespace                                                    │
│                                                                          │
│  Promtail (DaemonSet) ──▶ Loki ──────────────────────────┐              │
│                                                           │              │
│  PodMonitors (TF) ──▶ Prometheus ◀── PrometheusRules (TF)             │
│       │                    │                               │              │
│       │                    ├──▶ Alertmanager               │              │
│       │                    │                               │              │
│  kube-state-metrics ───────┤                               │              │
│  node-exporter ────────────┘                               │              │
│                                                             ▼              │
│  Dashboard ConfigMaps (TF) ──────────────────────▶ Grafana                │
│     (sidecar auto-import)         Prometheus + Loki datasources          │
└──────────────────────────────────────────────────────────────────────────┘
```

**External URLs**

| Tool | URL | Default login |
|------|-----|---------------|
| Grafana | https://grafana.livingdevops.org | admin / admin123 |
| Prometheus | https://prometheus.livingdevops.org | — |

---

## Cluster layer — what runs in `monitoring`

Deployed by `eks/k8s-services/logging-monitoring/` via Helm.

### kube-prometheus-stack (v70)

| Component | Role |
|-----------|------|
| **Prometheus** | Time-series database; pulls metrics on a scrape interval |
| **Grafana** | Dashboards, Explore, alert visualization |
| **Alertmanager** | Receives firing alerts; routes to Slack/PagerDuty (routing minimal today) |
| **Prometheus Operator** | Manages CRDs: `PodMonitor`, `ServiceMonitor`, `PrometheusRule` |
| **node-exporter** | Node CPU, memory, disk, network (DaemonSet) |
| **kube-state-metrics** | Kubernetes object metrics (pod restarts, readiness, replicas) |

Prometheus config highlights:

- **Retention:** 15 days, max 10 GB
- **Storage:** 20 Gi EBS PVC (`gp2`)
- **Scrape selectors:** empty `{}` — accepts all PodMonitors cluster-wide
- **Grafana sidecar:** watches ConfigMaps labeled `grafana_dashboard: "1"`

### loki-stack (v2.10.2)

| Component | Role |
|-----------|------|
| **Loki** | Log aggregation and storage (7-day retention) |
| **Promtail** | DaemonSet; tails `/var/log/pods` on every node |

Grafana gets Loki as an additional datasource at `http://loki.monitoring.svc.cluster.local:3100` (UID: `loki`).

---

## App layer — wiring your microservices

All Terraform lives in `infra/observability/`:

```
infra/observability/
├── podmonitors.tf       # Scrape config per service
├── prometheusrules.tf   # Recording rules + alerts
├── dashboards.tf        # Grafana ConfigMaps from JSON files
├── variables.tf         # Service ports, namespaces
└── dashboards/
    ├── generate.py              # Regenerate operational dashboards
    ├── ecommerce-overview.json  # Service RED
    ├── ecommerce-logs.json      # Loki explorer
    ├── ecommerce-microservices.json
    ├── ecommerce-databases.json
    └── ecommerce-business.json

dashboards/                      # SRE teaching dashboards (repo root under eks-microservice-implementation)
├── generate.py
├── README.md
└── 00-sre-overview.json … 07-sre-logs-incidents.json
```

Apply:

```bash
cd eks-microservice-implementation/infra/observability
terraform init
terraform apply
```

---

## Step 1 — Instrument apps (`/metrics`)

Each microservice exposes Prometheus metrics at `GET /metrics`:

| Service | Port | Library | Notable metrics |
|---------|------|---------|-----------------|
| product-service | 8001 | Go `client_golang` | `http_requests_total`, `product_queries_total`, `database_query_duration_seconds` |
| user-service | 8002 | Node `prom-client` | HTTP RED + `users_registered_total`, `user_logins_total` |
| cart-service | 8003 | Node `prom-client` | HTTP RED (label `status_code`, not `status`) |
| order-service | 8004 | Go `client_golang` | HTTP RED + `orders_created_total`, `order_value_total` |
| payment-service | 8005 | Python `prometheus_flask_exporter` | HTTP RED + `payments_processed_total{status}` |
| notification-service | 8006 | Python `prometheus_flask_exporter` | HTTP RED |
| api-gateway | 80 | nginx | `/metrics` (may show `up=0` until nginx metrics enabled) |

Example — Go middleware increments counters on every request (`apps/services/product-service/middleware/metrics.go`):

- `http_requests_total{method, endpoint, status}`
- `http_request_duration_seconds_bucket{le, ...}` (histogram for latency)
- `http_requests_in_flight` (gauge)

Python/Node services follow the same RED pattern with their respective client libraries.

---

## Step 2 — PodMonitor (scrape discovery)

A **PodMonitor** tells Prometheus: *find pods with label `app=<service>` in namespace `ecommerce`, scrape container port at `/metrics`.*

Why PodMonitor instead of ServiceMonitor? Helm `Service` objects use unnamed ports; PodMonitor targets the container port directly.

| Service | Scrape port | Interval |
|---------|-------------|----------|
| product-service | 8001 | 15s |
| user-service | 8002 | 15s |
| cart-service | 8003 | 15s |
| order-service | 8004 | 15s |
| payment-service | 8005 | 15s |
| notification-service | 8006 | 15s |
| api-gateway | 80 | 30s |

**Critical relabeling** — pod label `app` becomes metric label `service`:

```hcl
relabelings = [
  { sourceLabels = ["__meta_kubernetes_pod_label_app"], targetLabel = "service" },
  { sourceLabels = ["__meta_kubernetes_namespace"],     targetLabel = "namespace" },
]
```

All dashboards and alerts filter on `service` and `namespace="ecommerce"`.

Verify scraping:

```bash
kubectl get podmonitors -n monitoring -l app.kubernetes.io/part-of=ecommerce

kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090:9090
# http://localhost:9090/targets — filter for ecommerce
```

Useful PromQL:

```promql
up{namespace="ecommerce", service="product-service"}
ecommerce:http_request_rate:5m
```

---

## Step 3 — PrometheusRules (pre-compute + alert)

Four rule groups in `prometheusrules.tf`, scoped to `namespace="ecommerce"`.

### Recording rules (dashboard performance)

Pre-computed every 30s so Grafana panels stay fast:

| Recorded metric | Meaning |
|-----------------|---------|
| `ecommerce:http_request_rate:5m` | Requests/sec per service |
| `ecommerce:http_error_rate:5m` | 5xx fraction per service |
| `ecommerce:http_latency_p95:5m` | 95th percentile latency per service |

Error rate handles both Go/Python (`status`) and Node (`status_code`) label conventions.

### Alert rules (symptom-based)

| Alert | Condition | Severity |
|-------|-----------|----------|
| `EcommerceServiceDown` | `up == 0` for 2m | critical |
| `EcommerceHighErrorRate` | 5xx > 5% for 5m | warning |
| `EcommerceHighLatency` | p95 > 1s for 10m | warning |
| `EcommercePodCrashLooping` | >3 restarts in 15m | warning |
| `EcommerceHighPaymentFailureRate` | failures > 10% for 5m | warning |
| `EcommerceNoPaymentsProcessed` | zero payments for 15m | info |
| `EcommerceRabbitMQDown` | RabbitMQ pod not ready | critical |
| `EcommerceRedisDown` | Redis pod not ready | critical |
| `EcommerceCNPGClusterUnhealthy` | Postgres replication issue | warning |

**Alert pipeline:**

```
PrometheusRule → Prometheus evaluates → pending (for: duration) → firing → Alertmanager
```

View rules:

```bash
kubectl get prometheusrules -n monitoring ecommerce-app-rules
```

---

## Step 4 — Grafana dashboards

JSON files are loaded as ConfigMaps with label `grafana_dashboard: "1"`. The Grafana sidecar imports them automatically into folders via annotation `k8s-sidecar-target-directory`.

`dashboards.tf` auto-discovers:

- `infra/observability/dashboards/ecommerce-*.json` → folder **ecommerce**
- `dashboards/[0-9]*-sre-*.json` → folder **sre-teaching**

### Operational dashboards (`ecommerce` folder)

| Dashboard | UID | Use when |
|-----------|-----|----------|
| Ecommerce — Service RED | `ecommerce-red` | First stop in any incident |
| Ecommerce — All Microservices | `ecommerce-microservices` | Compare all 7 services side-by-side |
| Ecommerce — Databases & Dependencies | `ecommerce-databases` | Redis, RabbitMQ, CNPG, DB query latency |
| Ecommerce — Business Metrics | `ecommerce-business` | Orders, payments, registrations |
| Ecommerce — Logs (Loki) | `ecommerce-logs` | Log volume, errors, live tail |

### SRE teaching dashboards (`sre-teaching` folder)

| Dashboard | UID | Concept |
|-----------|-----|---------|
| SRE Teaching — Overview | `sre-overview` | Curriculum map |
| Golden Signals (RED) | `sre-golden-signals` | Rate, Errors, Duration |
| USE Method (Kubernetes) | `sre-use-kubernetes` | Utilization, Saturation, Errors |
| SLO & Error Budget | `sre-slo-error-budget` | SLI/SLO, burn rate |
| Alerting & Incidents | `sre-alerting` | Firing alerts, triage |
| Dependencies & Blast Radius | `sre-dependencies` | Cascade failures |
| Business SLIs | `sre-business-slis` | Customer-facing metrics |
| Logs for Incidents | `sre-logs-incidents` | Loki during incidents |

Regenerate dashboards:

```bash
# Operational
python3 infra/observability/dashboards/generate.py

# SRE teaching
python3 dashboards/generate.py

# Deploy
cd infra/observability && terraform apply
```

Verify:

```bash
kubectl get cm -n monitoring -l grafana_dashboard=1,app.kubernetes.io/part-of=ecommerce
```

---

## Metrics flow (one request, end to end)

1. `GET /products` hits **product-service** → middleware increments `http_requests_total` and observes latency histogram
2. Every **15s**, Prometheus scrapes `pod-ip:8001/metrics`
3. PodMonitor relabeling adds `service="product-service"`, `namespace="ecommerce"`
4. Recording rule computes `ecommerce:http_request_rate:5m{service="product-service"}`
5. Grafana dashboard plots the recorded metric
6. If 5xx rate > 5% for 5 minutes → `EcommerceHighErrorRate` fires

---

## Logs flow

No per-app configuration required.

```
container stdout/stderr
        ↓
kubelet (/var/log/pods/...)
        ↓
Promtail DaemonSet (every node)
        ↓
Loki (monitoring namespace)
        ↓
Grafana → Loki datasource → dashboards / Explore
```

Promtail attaches labels: `namespace`, `pod`, `app`, `container`.

**Explore examples:**

```logql
{namespace="ecommerce"} |~ "(?i)error"
{namespace="ecommerce", app="payment-service"} |~ "failed"
{namespace="ecommerce", app="order-service"} | json
```

---

## The RED method

Every request-serving service should expose these three signals:

| Signal | Question | Your metric |
|--------|----------|-------------|
| **R**ate | How many requests/sec? | `ecommerce:http_request_rate:5m` |
| **E**rrors | What fraction fail? | `ecommerce:http_error_rate:5m` |
| **D**uration | How slow? | `ecommerce:http_latency_p95:5m` |

CPU and memory (USE method) come from node-exporter and kube-state-metrics on separate dashboards.

**Incident workflow:**

1. **RED dashboard** — which service?
2. **Dependencies dashboard** — Redis/RabbitMQ/CNPG down?
3. **Logs dashboard** — why? (search for `error`, `timeout`, `connection refused`)

---

## What is monitored vs gaps

| Component | How | Gap |
|-----------|-----|-----|
| 6 microservices + api-gateway | PodMonitor → `/metrics` | api-gateway needs nginx metrics config |
| Postgres (CNPG) | App `database_query_duration_seconds` + pod readiness | CNPG PodMonitor disabled in Helm |
| Redis / RabbitMQ | kube-state-metrics pod readiness | No dedicated exporters |
| Kubernetes cluster | kube-prometheus-stack default rules | Covered |
| Distributed traces | — | Not implemented (no Tempo/Jaeger) |

---

## Adding a new microservice

1. Add Prometheus client + `GET /metrics` in the app
2. Add the service to `services` map in `infra/observability/variables.tf`
3. `terraform apply` — PodMonitor created automatically
4. Optional: add business metrics to `prometheusrules.tf` and dashboard JSON
5. Logs — automatic via Promtail (`app` label)

---

## Deploy order (context)

Monitoring is deployed in two steps (see `docs/DEPLOYMENT-SEQUENCE.md`):

| Step | Path | What |
|------|------|------|
| 8 | `eks/k8s-services/logging-monitoring/` | Cluster LGTM stack |
| 18 | `infra/observability/` | App scrape rules, alerts, dashboards |

Step 18 requires the monitoring stack (step 8) and running ecommerce pods (Helm step 16).

---

## Tear down

App wiring only (cluster stack unaffected):

```bash
cd eks-microservice-implementation/infra/observability
terraform destroy
```

Full cluster monitoring:

```bash
terraform -chdir=eks/k8s-services/logging-monitoring destroy
```

---

## Reference files

| Topic | Path |
|-------|------|
| Cluster Helm install | `eks/k8s-services/logging-monitoring/main.tf` |
| App Terraform module | `infra/observability/` |
| Standalone Prometheus config (reference) | `apps/monitoring/prometheus/` |
| SRE dashboard curriculum | `dashboards/README.md` |
| Terraform module quick reference | `infra/observability/README.md` |
