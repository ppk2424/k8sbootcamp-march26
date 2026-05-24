#!/usr/bin/env python3
"""Generate SRE teaching Grafana dashboards for the ecommerce platform."""

import json
from pathlib import Path

OUT = Path(__file__).parent
PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
NS = "ecommerce"


def base(title, uid, tags, description="", links=None):
    return {
        "annotations": {"list": []},
        "description": description,
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "links": links or [],
        "refresh": "30s",
        "schemaVersion": 38,
        "style": "dark",
        "tags": tags,
        "templating": {"list": []},
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "title": title,
        "uid": uid,
        "version": 1,
        "panels": [],
    }


def text(content, x, y, w=24, h=3, title=""):
    return {
        "type": "text",
        "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "transparent": True,
        "options": {"mode": "markdown", "content": content},
    }


def stat(title, expr, x, y, w=6, h=4, unit="short", thresholds=None, legend=""):
    fc = {"defaults": {"unit": unit, "decimals": 2}}
    if thresholds:
        fc["defaults"]["thresholds"] = thresholds
    return {
        "type": "stat",
        "title": title,
        "datasource": PROM,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": fc,
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value"},
        "targets": [{"expr": expr, "legendFormat": legend or title, "refId": "A"}],
    }


def timeseries(title, expr, x, y, w=12, h=8, unit="short", legend="{{service}}"):
    return {
        "type": "timeseries",
        "title": title,
        "datasource": PROM,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit, "custom": {"drawStyle": "line", "fillOpacity": 10, "lineInterpolation": "smooth"}}},
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max"]}},
        "targets": [{"expr": expr, "legendFormat": legend, "refId": "A"}],
    }


def table(title, expr, x, y, w=24, h=8, fmt="table"):
    return {
        "type": fmt,
        "title": title,
        "datasource": PROM,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": {"custom": {"align": "auto"}}},
        "options": {"showHeader": True, "sortBy": [{"desc": True, "displayName": "Value"}]},
        "targets": [{"expr": expr, "legendFormat": "", "refId": "A", "format": "table", "instant": True}],
    }


def gauge(title, expr, x, y, w=6, h=6, unit="percentunit", max_val=1):
    return {
        "type": "gauge",
        "title": title,
        "datasource": PROM,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": 0,
                "max": max_val,
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "red", "value": None},
                        {"color": "yellow", "value": 0.995},
                        {"color": "green", "value": 0.999},
                    ],
                },
            }
        },
        "targets": [{"expr": expr, "refId": "A"}],
    }


def dashboard_links():
    return [
        {"title": "SRE Overview", "url": "/d/sre-overview", "type": "link", "icon": "dashboard"},
        {"title": "Golden Signals (RED)", "url": "/d/sre-golden-signals", "type": "link", "icon": "dashboard"},
        {"title": "USE Method (K8s)", "url": "/d/sre-use-kubernetes", "type": "link", "icon": "dashboard"},
        {"title": "SLO & Error Budget", "url": "/d/sre-slo-error-budget", "type": "link", "icon": "dashboard"},
        {"title": "Alerting & Incidents", "url": "/d/sre-alerting", "type": "link", "icon": "dashboard"},
        {"title": "Dependencies", "url": "/d/sre-dependencies", "type": "link", "icon": "dashboard"},
        {"title": "Business SLIs", "url": "/d/sre-business-slis", "type": "link", "icon": "dashboard"},
    ]


def build_overview():
    d = base(
        "SRE Teaching — Overview",
        "sre-overview",
        ["sre", "teaching", "ecommerce"],
        "Curriculum map for Site Reliability Engineering concepts on the ecommerce EKS platform.",
        dashboard_links(),
    )
    d["panels"] = [
        text(
            """# Site Reliability Engineering — Dashboard Curriculum

This folder teaches core SRE ideas using **live data** from the ecommerce microservices on EKS.

| Dashboard | SRE concept | What you learn |
|-----------|-------------|----------------|
| **Golden Signals (RED)** | Rate, Errors, Duration | User-facing service health — the minimum set every on-call engineer needs |
| **USE Method (K8s)** | Utilization, Saturation, Errors | Infrastructure capacity — when the *platform* is the bottleneck |
| **SLO & Error Budget** | SLI, SLO, error budget, burn rate | Reliability targets and how much failure you can afford |
| **Alerting & Incidents** | Symptom-based alerts, severity | What is firing right now and how alerts map to user pain |
| **Dependencies** | Blast radius, cascading failure | Redis, RabbitMQ, Postgres — shared fate between services |
| **Business SLIs** | User-journey metrics | Orders and payments — reliability from the customer's perspective |

**Golden rule:** Measure symptoms (what users feel), alert on symptoms, then use logs/traces/metrics to find causes.

**Deploy:** `terraform apply` in `infra/observability/` or import JSON from Grafana UI → Dashboards → Import.
""",
            0,
            0,
            h=12,
        ),
        stat("Services Up (ecommerce)", f'sum(up{{namespace="{NS}"}} == 1)', 0, 12, unit="short"),
        stat("Request rate (req/s)", f'sum(ecommerce:http_request_rate:5m)', 6, 12, unit="reqps"),
        stat("5xx error rate", f'avg(ecommerce:http_error_rate:5m)', 12, 12, unit="percentunit",
             thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 0.01}, {"color": "red", "value": 0.05}]}),
        stat("Firing alerts", 'count(ALERTS{alertstate="firing"}) or vector(0)', 18, 12, unit="short",
             thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]}),
        timeseries("Platform snapshot — request rate by service", f'ecommerce:http_request_rate:5m{{namespace="{NS}"}}', 0, 16, w=24, legend="{{service}}"),
    ]
    return d


def build_red():
    d = base(
        "SRE Teaching — Golden Signals (RED)",
        "sre-golden-signals",
        ["sre", "teaching", "red", "ecommerce"],
        "RED method: Rate, Errors, Duration — the three golden signals for user-facing services.",
        dashboard_links(),
    )
    d["templating"]["list"] = [{
        "current": {"selected": False, "text": "All", "value": "$__all"},
        "datasource": PROM,
        "definition": f'label_values(up{{namespace="{NS}"}}, service)',
        "hide": 0, "includeAll": True, "label": "service", "multi": True, "name": "service",
        "query": {"query": f'label_values(up{{namespace="{NS}"}}, service)', "refId": "A"},
        "refresh": 2, "type": "query",
    }]
    d["panels"] = [
        text(
            """## RED Method (Google SRE)

For **user-facing services**, monitor three signals:

- **Rate** — How much demand? (requests/sec, transactions/sec)
- **Errors** — What fraction fail? (5xx ratio, failed business operations)
- **Duration** — How long do requests take? (p50/p95/p99 latency)

**Why not CPU/memory?** Resource metrics tell you about *machines*, not *users*. A service can be slow while CPU looks fine (DB lock, downstream timeout).

**Exercise:** Pick a service in the dropdown. If error rate spikes but rate is flat → quality problem. If rate drops and errors spike → overload or dependency failure.
""",
            0, 0, h=5,
        ),
        stat("Rate — requests/sec", 'sum(ecommerce:http_request_rate:5m{service=~"$service"})', 0, 5, unit="reqps"),
        stat("Errors — 5xx ratio", 'avg(ecommerce:http_error_rate:5m{service=~"$service"})', 6, 5, unit="percentunit",
             thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 0.01}, {"color": "red", "value": 0.05}]}),
        stat("Duration — p95 (s)", 'max(ecommerce:http_latency_p95:5m{service=~"$service"})', 12, 5, unit="s",
             thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "yellow", "value": 0.5}, {"color": "red", "value": 1}]}),
        stat("In-flight requests", f'sum(http_requests_in_flight{{namespace="{NS}",service=~"$service"}})', 18, 5, unit="short"),
        timeseries("Rate by service", 'ecommerce:http_request_rate:5m{service=~"$service"}', 0, 9, legend="{{service}}"),
        timeseries("Error rate (5xx) by service", 'ecommerce:http_error_rate:5m{service=~"$service"}', 12, 9, unit="percentunit", legend="{{service}}"),
        timeseries("Latency p50 / p95 / p99", f'''histogram_quantile(0.50, sum by (le, service) (rate(http_request_duration_seconds_bucket{{namespace="{NS}",service=~"$service"}}[5m])))''', 0, 17, w=8, unit="s", legend="p50 {{service}}"),
        timeseries("", f'''histogram_quantile(0.95, sum by (le, service) (rate(http_request_duration_seconds_bucket{{namespace="{NS}",service=~"$service"}}[5m])))''', 8, 17, w=8, unit="s", legend="p95 {{service}}"),
        timeseries("", f'''histogram_quantile(0.99, sum by (le, service) (rate(http_request_duration_seconds_bucket{{namespace="{NS}",service=~"$service"}}[5m])))''', 16, 17, w=8, unit="s", legend="p99 {{service}}"),
        text(
            """**Percentiles matter:** p95/p99 reveal tail latency that averages hide. SLOs are often written on p99 (e.g. 99% of requests < 500ms).

**Recording rules:** `ecommerce:http_*` metrics are pre-computed in PrometheusRule `ecommerce-app-rules` — faster dashboards, consistent alert thresholds.
""",
            0, 25, h=3,
        ),
    ]
    d["panels"][7]["title"] = "Latency p50"
    d["panels"][8]["title"] = "Latency p95"
    d["panels"][9]["title"] = "Latency p99"
    return d


def build_use():
    d = base(
        "SRE Teaching — USE Method (Kubernetes)",
        "sre-use-kubernetes",
        ["sre", "teaching", "use", "kubernetes"],
        "USE method for infrastructure: Utilization, Saturation, Errors.",
        dashboard_links(),
    )
    d["templating"]["list"] = [{
        "current": {"selected": False, "text": "ecommerce", "value": NS},
        "hide": 0, "label": "namespace", "name": "namespace", "options": [{"text": NS, "value": NS}],
        "query": NS, "type": "custom",
    }]
    d["panels"] = [
        text(
            """## USE Method (Brendan Gregg / Google SRE)

For **infrastructure resources** (CPU, memory, disk, network):

- **Utilization** — Average busy time (e.g. CPU % of limit)
- **Saturation** — Queue depth / work waiting (pending pods, throttling, OOM pressure)
- **Errors** — Hard failures (pod restarts, evictions, FailedScheduling)

**RED vs USE:** RED = services (user view). USE = resources (platform view). Both are needed.

**Exercise:** High CPU utilization + pending pods → scale out (Karpenter). High memory + restarts → OOM — raise limits or fix leak.
""",
            0, 0, h=5,
        ),
        stat("Pending pods", 'sum(kube_pod_status_phase{namespace="$namespace",phase="Pending"})', 0, 5),
        stat("Failed pods", 'sum(kube_pod_status_phase{namespace="$namespace",phase="Failed"})', 6, 5),
        stat("Restarts (15m)", 'sum(increase(kube_pod_container_status_restarts_total{namespace="$namespace"}[15m]))', 12, 5),
        stat("Karpenter nodes", 'count(kube_node_info{node=~".+"}) and on(node) count by (node) (kube_node_labels{label_karpenter_sh_nodepool!=""}) or vector(0)', 18, 5),
        timeseries("CPU utilization vs requests", '''sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="$namespace",container!="",container!="POD"}[5m]))
/ on(pod) group_left sum by (pod) (kube_pod_container_resource_requests{namespace="$namespace",resource="cpu",container!=""})''', 0, 9, unit="percentunit", legend="{{pod}}"),
        timeseries("Memory utilization vs limits", '''sum by (pod) (container_memory_working_set_bytes{namespace="$namespace",container!="",container!="POD"})
/ on(pod) group_left sum by (pod) (kube_pod_container_resource_limits{namespace="$namespace",resource="memory",container!=""})''', 12, 9, unit="percentunit", legend="{{pod}}"),
        timeseries("CPU throttling (seconds/s)", 'sum by (pod) (rate(container_cpu_cfs_throttled_seconds_total{namespace="$namespace",container!=""}[5m]))', 0, 17, legend="{{pod}}"),
        timeseries("Pod restarts over time", 'increase(kube_pod_container_status_restarts_total{namespace="$namespace"}[15m])', 12, 17, legend="{{pod}}"),
        timeseries("Node CPU allocatable usage", '1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))', 0, 25, w=12, unit="percentunit", legend="{{node}}"),
        timeseries("Node memory pressure", '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))', 12, 25, w=12, unit="percentunit", legend="{{node}}"),
    ]
    return d


def build_slo():
    d = base(
        "SRE Teaching — SLO & Error Budget",
        "sre-slo-error-budget",
        ["sre", "teaching", "slo", "sli"],
        "SLI/SLO concepts, availability target, and error budget consumption.",
        dashboard_links(),
    )
    avail_sli = f'''1 - (
  sum(rate(http_requests_total{{namespace="{NS}",status=~"5.."}}[5m]))
  / sum(rate(http_requests_total{{namespace="{NS}"}}[5m]))
)'''
    d["panels"] = [
        text(
            """## SLI, SLO, Error Budget

- **SLI** (Indicator) — A measurable aspect of reliability (e.g. % successful requests)
- **SLO** (Objective) — Target for the SLI (e.g. 99.9% availability over 30 days)
- **Error budget** — Allowed unreliability: `1 - SLO` (99.9% → 0.1% bad requests)

**Burn rate:** How fast you consume the budget. Fast burn → page immediately. Slow burn → ticket.

This dashboard uses a **99.9% availability SLO** on HTTP success (non-5xx). Adjust targets in panels for your team agreement.

**Exercise:** If availability SLI is 99.95% but SLO is 99.9%, you still have budget. At 99.5%, you've exhausted budget — freeze features, focus on reliability.
""",
            0, 0, h=6,
        ),
        gauge("Availability SLI (5m window)", avail_sli, 0, 6, unit="percentunit"),
        stat("SLO target", "0.999", 6, 6, unit="percentunit"),
        stat("Error budget headroom", f"({avail_sli}) - 0.999", 12, 6, unit="percentunit"),
        stat("5xx req/s (budget consumption)", f'sum(rate(http_requests_total{{namespace="{NS}",status=~"5.."}}[5m]))', 18, 6, unit="reqps"),
        timeseries("Availability SLI over time", avail_sli, 0, 12, w=12, unit="percentunit", legend="availability"),
        timeseries("Latency SLI — % requests under 1s", f'''sum(rate(http_request_duration_seconds_bucket{{namespace="{NS}",le="1"}}[5m]))
/ sum(rate(http_request_duration_seconds_count{{namespace="{NS}"}}[5m]))''', 12, 12, w=12, unit="percentunit", legend="under 1s"),
        timeseries("Fast burn — 5xx rate (14.4× budget burn indicator)", f'''sum(rate(http_requests_total{{namespace="{NS}",status=~"5.."}}[5m]))
/ sum(rate(http_requests_total{{namespace="{NS}"}}[5m])) / 0.001''', 0, 20, w=12, unit="short", legend="burn multiplier"),
        timeseries("Slow burn — 5xx rate (1h smoothed)", f'''sum(rate(http_requests_total{{namespace="{NS}",status=~"5.."}}[1h]))
/ sum(rate(http_requests_total{{namespace="{NS}"}}[1h])) / 0.001''', 12, 20, w=12, unit="short", legend="1h burn"),
        text(
            """**Multi-window burn alerts** (Google SRE Workbook): Compare short and long windows — e.g. 5m and 1h — to catch both sudden incidents and gradual degradation without alert fatigue.

PrometheusRule alerts in `ecommerce-app-rules` implement symptom thresholds: `EcommerceHighErrorRate` (>5% 5xx), `EcommerceHighLatency` (p95 > 1s).
""",
            0, 28, h=3,
        ),
    ]
    return d


def build_alerting():
    d = base(
        "SRE Teaching — Alerting & Incident Readiness",
        "sre-alerting",
        ["sre", "teaching", "alerting", "incident"],
        "Symptom-based alerting, severity, and incident triage using Prometheus/Alertmanager.",
        dashboard_links(),
    )
    d["panels"] = [
        text(
            """## Effective Alerting (SRE)

Good alerts are **actionable**, **symptom-based**, and **owned**:

1. **Symptom** — User can't checkout (high 5xx on order-service), not "CPU > 80%"
2. **Page vs ticket** — Critical/user-facing → page on-call. Info → ticket.
3. **Runbook** — Every alert links to "what do I do first?"

**Alert pipeline:** PrometheusRule → Prometheus evaluates → Alertmanager routes → PagerDuty/Slack.

**Exercise:** When `EcommerceServiceDown` fires, check RED dashboard for that service, then Dependencies dashboard for Redis/RabbitMQ/CNPG.
""",
            0, 0, h=6,
        ),
        stat("Firing alerts (all)", 'count(ALERTS{alertstate="firing"}) or vector(0)', 0, 6,
             thresholds={"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]}),
        stat("Pending alerts", 'count(ALERTS{alertstate="pending"}) or vector(0)', 6, 6),
        stat("Critical severity", 'count(ALERTS{alertstate="firing",severity="critical"}) or vector(0)', 12, 6),
        stat("Ecommerce team alerts", 'count(ALERTS{alertstate="firing",team="ecommerce"}) or vector(0)', 18, 6),
        table("Firing alerts — detail", 'ALERTS{alertstate="firing"}', 0, 10, h=10),
        timeseries("Alert events over time", 'changes(ALERTS_FOR_STATE{alertstate="firing"}[5m])', 0, 20, w=12, legend="{{alertname}}"),
        timeseries("Ecommerce error rate (symptom)", 'ecommerce:http_error_rate:5m', 12, 20, w=12, unit="percentunit", legend="{{service}}"),
        text(
            """### Ecommerce alert catalog (`ecommerce-app-rules`)

| Alert | Severity | Symptom |
|-------|----------|---------|
| `EcommerceServiceDown` | critical | Scrape target down 2m |
| `EcommerceHighErrorRate` | warning | 5xx > 5% for 5m |
| `EcommerceHighLatency` | warning | p95 > 1s for 10m |
| `EcommercePodCrashLooping` | warning | >3 restarts in 15m |
| `EcommerceHighPaymentFailureRate` | warning | Payment failures > 10% |
| `EcommerceRabbitMQDown` / `EcommerceRedisDown` | critical | Dependency not ready |
""",
            0, 28, h=5,
        ),
    ]
    return d


def build_dependencies():
    d = base(
        "SRE Teaching — Dependencies & Blast Radius",
        "sre-dependencies",
        ["sre", "teaching", "dependencies", "cascade"],
        "Shared infrastructure: Redis, RabbitMQ, CNPG — cascading failure patterns.",
        dashboard_links(),
    )
    d["panels"] = [
        text(
            """## Dependencies & Cascading Failures

Microservices share fate through **shared dependencies**. One Redis outage can break cart-service → order-service → payment flow.

**Blast radius:** Map which services fail when a dependency fails.

| Dependency | If down | Affected services |
|------------|---------|-------------------|
| Redis | Cart can't store items | cart-service, order-service (checkout) |
| RabbitMQ | Events not delivered | order-service, notification-service |
| CNPG Postgres | Data unavailable | product, user, order, payment |
| product-service | Catalog/stock unknown | cart, order, api-gateway |

**Exercise:** Simulate Redis failure (`kubectl scale deploy redis -n ecommerce --replicas=0`). Watch error rate propagate upstream on RED dashboard.
""",
            0, 0, h=7,
        ),
        stat("Redis ready", f'kube_pod_status_ready{{namespace="{NS}",pod=~"redis-.*",condition="true"}}', 0, 7),
        stat("RabbitMQ ready", f'kube_pod_status_ready{{namespace="{NS}",pod=~"rabbitmq-.*",condition="true"}}', 6, 7),
        stat("CNPG clusters ready", f'count(cnpg_collector_up{{namespace="{NS}"}} == 1) or vector(0)', 12, 7),
        stat("Postgres connections (all)", f'sum(database_connections_active{{namespace="{NS}"}}) or vector(0)', 18, 7),
        timeseries("DB query latency p95 by service", f'''histogram_quantile(0.95, sum by (le, service) (rate(database_query_duration_seconds_bucket{{namespace="{NS}"}}[5m])))''', 0, 11, unit="s", legend="{{service}}"),
        timeseries("HTTP errors — cart vs order (cascade indicator)", f'ecommerce:http_error_rate:5m{{service=~"cart-service|order-service|payment-service"}}', 12, 11, unit="percentunit", legend="{{service}}"),
        timeseries("CNPG — collector up per cluster", f'cnpg_collector_up{{namespace="{NS}"}}', 0, 19, legend="{{cluster}}"),
        timeseries("RabbitMQ / Redis pod restarts", f'increase(kube_pod_container_status_restarts_total{{namespace="{NS}",pod=~"redis-.*|rabbitmq-.*"}}[15m])', 12, 19, legend="{{pod}}"),
    ]
    return d


def build_business():
    d = base(
        "SRE Teaching — Business SLIs (Ecommerce)",
        "sre-business-slis",
        ["sre", "teaching", "business", "sli"],
        "User-journey metrics: orders, payments, products — reliability from the customer view.",
        dashboard_links(),
    )
    d["panels"] = [
        text(
            """## Business SLIs

Technical metrics (CPU, memory) don't tell you if **customers can buy things**. Business SLIs tie reliability to revenue:

- **Checkout success rate** — orders completed / orders attempted
- **Payment success rate** — payments `status=success` / total payments
- **Catalog availability** — product API success rate

These align engineering with product. An SLO like "99.5% of payment attempts succeed" is negotiable with stakeholders.

**Exercise:** Compare payment failure rate here with `EcommerceHighPaymentFailureRate` alert (>10% for 5m).
""",
            0, 0, h=6,
        ),
        stat("Orders created / min", f'sum(rate(orders_created_total{{namespace="{NS}"}}[5m])) * 60', 0, 6, unit="short"),
        stat("Orders completed / min", f'sum(rate(orders_completed_total{{namespace="{NS}"}}[5m])) * 60', 6, 6, unit="short"),
        stat("Payment success rate", f'''sum(rate(payments_processed_total{{namespace="{NS}",status="success"}}[5m]))
/ sum(rate(payments_processed_total{{namespace="{NS}"}}[5m]))''', 12, 6, unit="percentunit"),
        stat("Payment failures / min", f'sum(rate(payments_processed_total{{namespace="{NS}",status="failed"}}[5m])) * 60', 18, 6, unit="short"),
        timeseries("Order funnel — created vs completed vs cancelled", f'sum(rate(orders_created_total{{namespace="{NS}"}}[5m]))', 0, 10, w=8, legend="created"),
        timeseries("", f'sum(rate(orders_completed_total{{namespace="{NS}"}}[5m]))', 8, 10, w=8, legend="completed"),
        timeseries("", f'sum(rate(orders_cancelled_total{{namespace="{NS}"}}[5m]))', 16, 10, w=8, legend="cancelled"),
        timeseries("Payments by status", f'sum by (status) (rate(payments_processed_total{{namespace="{NS}"}}[5m]))', 0, 18, legend="{{status}}"),
        timeseries("Product queries by type", f'sum by (query_type) (rate(product_queries_total{{namespace="{NS}"}}[5m]))', 12, 18, legend="{{query_type}}"),
        timeseries("Payment processing duration p95", f'''histogram_quantile(0.95, sum by (le) (rate(payment_processing_duration_seconds_bucket{{namespace="{NS}"}}[5m])))''', 0, 26, w=12, unit="s"),
        timeseries("Order value rate (currency units/s)", f'sum(rate(order_value_total{{namespace="{NS}"}}[5m]))', 12, 26, w=12),
    ]
    d["panels"][5]["title"] = "Orders created rate"
    d["panels"][6]["title"] = "Orders completed rate"
    d["panels"][7]["title"] = "Orders cancelled rate"
    return d


def build_logs_sre():
    d = base(
        "SRE Teaching — Logs for Incidents (Loki)",
        "sre-logs-incidents",
        ["sre", "teaching", "logs", "loki"],
        "Structured log exploration during incidents — correlate with metrics.",
        dashboard_links(),
    )
    d["templating"]["list"] = [
        {"current": {"text": NS, "value": NS}, "hide": 0, "label": "namespace", "name": "namespace", "options": [{"text": NS, "value": NS}], "query": NS, "type": "custom"},
        {"current": {"text": "", "value": ""}, "hide": 0, "label": "search", "name": "search", "options": [{"text": "", "value": ""}], "query": "", "type": "textbox"},
    ]
    d["panels"] = [
        text(
            """## Logs in the SRE Toolkit

**Metrics** tell you something is wrong. **Logs** tell you why.

During an incident:
1. Check RED dashboard for *which* service
2. Filter logs here by `app` label
3. Search for `error`, `timeout`, `connection refused`, status codes

Promtail ships all container logs to Loki automatically — no per-app config.
""",
            0, 0, h=4,
        ),
        {
            "type": "timeseries",
            "title": "Log volume by app",
            "datasource": LOKI,
            "gridPos": {"h": 6, "w": 24, "x": 0, "y": 4},
            "targets": [{"expr": 'sum by (app) (count_over_time({namespace="$namespace"} |~ "(?i)$search" [1m]))', "legendFormat": "{{app}}", "refId": "A"}],
        },
        {
            "type": "timeseries",
            "title": "Error log rate",
            "datasource": LOKI,
            "gridPos": {"h": 6, "w": 24, "x": 0, "y": 10},
            "targets": [{"expr": 'sum by (app) (count_over_time({namespace="$namespace"} |~ "(?i)(error|fatal|panic|5[0-9]{2})" |~ "(?i)$search" [1m]))', "legendFormat": "{{app}}", "refId": "A"}],
        },
        {
            "type": "logs",
            "title": "Live tail — ecommerce",
            "datasource": LOKI,
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 16},
            "options": {"showTime": True, "showLabels": True, "sortOrder": "Descending", "wrapLogMessage": True},
            "targets": [{"expr": '{namespace="$namespace"} |~ "(?i)$search"', "refId": "A"}],
        },
    ]
    return d


DASHBOARDS = [
    ("00-sre-overview.json", build_overview),
    ("01-sre-golden-signals-red.json", build_red),
    ("02-sre-use-method-kubernetes.json", build_use),
    ("03-sre-slo-error-budget.json", build_slo),
    ("04-sre-alerting-incidents.json", build_alerting),
    ("05-sre-dependencies-blast-radius.json", build_dependencies),
    ("06-sre-business-slis.json", build_business),
    ("07-sre-logs-incidents.json", build_logs_sre),
]


def main():
    for filename, builder in DASHBOARDS:
        path = OUT / filename
        data = builder()
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
