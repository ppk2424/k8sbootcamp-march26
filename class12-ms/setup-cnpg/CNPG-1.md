# CNPG Setup — Local (kind) with Primary + Replicas

---

## What You Need Before Starting

- Docker running
- `kind` installed
- `kubectl` installed
- `helm` installed

---

## Step 1 — Create a kind Cluster

```bash
kind create cluster --name cnpg-demo
```

Verify it's up:

```bash
kubectl cluster-info --context kind-cnpg-demo
```

---

## Step 2 — Install the CNPG Operator

CNPG operator runs inside your cluster. It watches for `Cluster` resources and manages Postgres for you.

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm repo update

helm install cnpg \
  --namespace cnpg-system \
  --create-namespace \
  cnpg/cloudnative-pg
```

Verify the operator is running:

```bash
kubectl get pods -n cnpg-system
```

You should see one operator pod in `Running` state. That pod is now watching your entire cluster for CNPG resources.

---

## Step 3 — Create Your Postgres Cluster

Create a file called `cluster.yaml`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: postgres-demo
  namespace: default
spec:
  instances: 3

  postgresql:
    parameters:
      max_connections: "200"

  storage:
    size: 1Gi
```

Apply it:

```bash
kubectl apply -f cluster.yaml
```

---

## Step 4 — Watch It Come Up

```bash
kubectl get cluster postgres-demo -w
```

You will see it go through phases:

```
NAME            AGE   INSTANCES   READY   STATUS
postgres-demo   10s   3           0       Setting up primary
postgres-demo   30s   3           1       Creating replica
postgres-demo   60s   3           3       Cluster in healthy state
```

Three pods will come up:

```bash
kubectl get pods
```

```
postgres-demo-1   1/1   Running   # PRIMARY
postgres-demo-2   1/1   Running   # REPLICA
postgres-demo-3   1/1   Running   # REPLICA
```

CNPG decides which is primary. You don't pick it manually.

---

## Step 5 — Understand What Got Created

CNPG created several things automatically. Look at them:

```bash
kubectl get services
```

You'll see three services:

| Service | Purpose |
|---|---|
| `postgres-demo-rw` | Connect here for **writes** (points to primary) |
| `postgres-demo-ro` | Connect here for **reads** (points to replicas) |
| `postgres-demo-r` | Points to all instances |

This is the key insight. Your app never talks to a pod directly. It talks to the service. When failover happens, the service automatically points to the new primary. Your app doesn't know anything changed.

---

## Step 6 — Connect to Your Cluster

CNPG stores credentials in a secret automatically:

```bash
kubectl get secret postgres-demo-app -o jsonpath='{.data.password}' | base64 -d
```

Now exec into the primary pod:

```bash
kubectl exec -it postgres-demo-1 -- psql -U app
```

Run a quick check:

```sql
SELECT pg_is_in_recovery();
```

Returns `f` (false) on primary — meaning it's not in recovery, it's the writer.

Now exec into a replica:

```bash
kubectl exec -it postgres-demo-2 -- psql -U app
```

```sql
SELECT pg_is_in_recovery();
```

Returns `t` (true) — it's a replica, receiving WAL from primary.

---

## Step 7 — Test Automatic Failover

This is where it gets interesting. Delete the primary pod:

```bash
kubectl delete pod postgres-demo-1
```

Watch what happens:

```bash
kubectl get cluster postgres-demo -w
```

CNPG will promote one of the replicas to primary within seconds. The `postgres-demo-rw` service now points to the new primary. The old pod comes back as a replica.

That's your RTO in action — seconds, not minutes.

---

## What You Just Built

```
kind cluster
    └── CNPG Operator (cnpg-system)
            └── Cluster: postgres-demo
                    ├── postgres-demo-1 (primary)
                    ├── postgres-demo-2 (replica)
                    ├── postgres-demo-3 (replica)
                    ├── Service: rw → primary
                    ├── Service: ro → replicas
                    └── Secret: credentials
```

---

## Next Step Options

- **Backup to S3** — add a `backup` section to the cluster spec + scheduled backups
- **PgBouncer Pooler** — add a `Pooler` resource for connection pooling
- **Simulate failures** — break things deliberately and watch CNPG recover

Which one do you want next?