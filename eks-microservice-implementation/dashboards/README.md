# SRE Teaching Dashboards

Grafana dashboards that teach **Site Reliability Engineering** principles using live metrics from the ecommerce platform on EKS.

Each dashboard includes **markdown teaching panels** (the *why*) plus **Prometheus/Loki queries** (the *how*).

---

## Dashboard catalog

| File | Grafana UID | SRE concept |
|------|-------------|-------------|
| `00-sre-overview.json` | `sre-overview` | Curriculum map + platform snapshot |
| `01-sre-golden-signals-red.json` | `sre-golden-signals` | **RED** — Rate, Errors, Duration |
| `02-sre-use-method-kubernetes.json` | `sre-use-kubernetes` | **USE** — Utilization, Saturation, Errors |
| `03-sre-slo-error-budget.json` | `sre-slo-error-budget` | **SLI/SLO**, error budget, burn rate |
| `04-sre-alerting-incidents.json` | `sre-alerting` | Symptom alerts, severity, triage |
| `05-sre-dependencies-blast-radius.json` | `sre-dependencies` | Cascading failures, Redis/RabbitMQ/CNPG |
| `06-sre-business-slis.json` | `sre-business-slis` | Orders, payments — customer-view reliability |
| `07-sre-logs-incidents.json` | `sre-logs-incidents` | Loki log exploration during incidents |

All dashboards cross-link to each other via the top navigation links.

---

## SRE concepts covered

### 1. Golden Signals (RED)

For **services** — what users experience:

- **Rate** — demand (`ecommerce:http_request_rate:5m`)
- **Errors** — failure fraction (`ecommerce:http_error_rate:5m`)
- **Duration** — latency percentiles (`http_request_duration_seconds_bucket`)

### 2. USE Method

For **infrastructure** — what the platform experiences:

- **Utilization** — CPU/memory vs requests/limits
- **Saturation** — pending pods, CPU throttling
- **Errors** — restarts, failed pods

### 3. SLI / SLO / Error Budget

- **SLI:** availability = 1 − (5xx / total requests)
- **SLO:** 99.9% availability (configurable in panels)
- **Error budget:** `SLI − SLO` headroom
- **Burn rate:** short vs long window 5xx comparison

### 4. Alerting

Maps to PrometheusRule `ecommerce-app-rules` in `infra/observability/prometheusrules.tf`:

- Symptom-based (5xx, latency, service down)
- Severity labels (`critical`, `warning`, `info`)
- Business alerts (payment failure rate)

### 5. Dependencies & blast radius

Shows how Redis, RabbitMQ, and CNPG failures propagate to cart → order → payment.

### 6. Business SLIs

User-journey metrics: `orders_*_total`, `payments_processed_total`, `product_queries_total`.

---

## Prerequisites

1. Cluster monitoring stack deployed: `eks/k8s-services/logging-monitoring/`
2. Ecommerce app running: `helm-ecommerce/`
3. App observability wired: `infra/observability/` (PodMonitors + recording rules)
4. Grafana: https://grafana.livingdevops.org (`admin` / `admin123`)

Datasources expected by the JSON:

| UID | Type | Source |
|-----|------|--------|
| `prometheus` | Prometheus | kube-prometheus-stack (default) |
| `loki` | Loki | logging-monitoring additionalDataSources |

---

## Deploy to Grafana

### Option A — Terraform (recommended)

SRE dashboards are loaded automatically when you apply observability:

```bash
cd eks-microservice-implementation/infra/observability
terraform init
terraform apply
```

ConfigMaps land in `monitoring` namespace with label `grafana_dashboard: "1"`. Grafana sidecar picks them up in folder `/tmp/dashboards/sre-teaching`.

### Option B — Manual import

Grafana UI → **Dashboards** → **New** → **Import** → upload any `*.json` from this folder.

### Option C — kubectl one-liner

```bash
for f in eks-microservice-implementation/dashboards/*.json; do
  name=$(basename "$f" .json)
  kubectl create configmap "sre-${name}" \
    --from-file="${name}.json=${f}" \
    -n monitoring \
    --dry-run=client -o yaml | \
  kubectl label --local -f - grafana_dashboard=1 -o yaml | \
  kubectl annotate --local -f - k8s-sidecar-target-directory=/tmp/dashboards/sre-teaching -o yaml | \
  kubectl apply -f -
done
```

---

## Regenerate dashboards

Edit `generate.py` (queries, teaching text, panels) then:

```bash
cd eks-microservice-implementation/dashboards
python3 generate.py
terraform -chdir=../infra/observability apply
```

---

## Learning path (bootcamp exercise)

1. **Baseline** — Open `SRE Overview`. Confirm services are up and request rate > 0.
2. **RED** — Filter to `order-service`. Note rate, errors, p95 latency.
3. **Break it** — Scale Redis to 0: `kubectl scale deploy redis -n ecommerce --replicas=0`
4. **Observe cascade** — RED on cart/order; Dependencies dashboard; Logs dashboard for connection errors.
5. **Alerts** — Check Alerting dashboard for firing rules.
6. **Recover** — `kubectl scale deploy redis -n ecommerce --replicas=1`
7. **SLO** — Discuss error budget consumed during the incident.
8. **Restore** — Scale Redis back; verify SLI returns above SLO.

---

## Related

- App RED dashboard (operational): `infra/observability/dashboards/ecommerce-overview.json`
- App logs dashboard: `infra/observability/dashboards/ecommerce-logs.json`
- Alert rules: `infra/observability/prometheusrules.tf`
- Metrics middleware: `apps/services/*/middleware/` and `apps/services/payment-service/app.py`
