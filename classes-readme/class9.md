# Class Notes — April 19, 2026
## LivingDevOps Bootcamp · Session 8

---

## Topics Covered

### 1. Root Cause: AWS Load Balancer Controller Auth Failure (Recap from Previous Class)

The load balancer controller failed to create an ALB because of a **pod restart timing issue**:

- The IAM role for the controller was created **after** the pods were already running
- On startup, the controller generates temporary credentials (as environment variables) using the OIDC-linked IAM role
- Since the role didn't exist yet when the pod started, the credentials were empty/invalid
- Even after adding the IAM role, the pod was still using its old (empty) credentials
- **Fix:** Restart the controller pods — they picked up the new IAM role and generated valid credentials automatically
- No config changes were needed — just `kubectl rollout restart`

**Lesson:** When using OIDC-based IAM roles for service accounts, always ensure the IAM role exists before deploying the pod that depends on it.

---

### 2. Ingress with AWS ALB — Terraform Deployment

The Kubernetes Ingress resource was moved from a manual `kubectl apply` to Terraform.

Key annotations used:

```yaml
kubernetes.io/ingress.class: alb
alb.ingress.kubernetes.io/scheme: internet-facing
alb.ingress.kubernetes.io/target-type: ip
```

**How traffic routing works:**

- The Ingress defines paths (`/` → frontend, `/api` → backend)
- The AWS Load Balancer Controller reads the Ingress and creates an ALB with matching rules and target groups
- Pod IPs are registered directly as ALB targets — the controller does this automatically, no manual target registration
- When a pod dies and a new one comes up with a different IP, the controller detects the change (via the Service selector) and updates the target group automatically
- Services are not the target — they are the **discovery mechanism** that tells the controller which pod IPs to register

---

### 3. ACM Certificate — DNS Validation via Terraform

To enable HTTPS, an ACM certificate must be requested and validated.

**Steps automated in Terraform:**

1. Pull the existing Route 53 hosted zone using a `data` source (the zone is pre-existing, not created here)
2. Request an ACM certificate for the subdomain (`app.domain.com`)
3. Set validation method to `DNS`
4. ACM creates a CNAME record in Route 53 — Terraform handles this automatically with `aws_acm_certificate_validation`
5. Output the certificate ARN for use in the Ingress

```hcl
resource "aws_acm_certificate" "app" {
  domain_name       = "app.${var.domain_name}"
  validation_method = "DNS"
}

resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for r in aws_acm_certificate.app.domain_validation_options : r.resource_record_name]
}
```

---

### 4. HTTPS Ingress Configuration

Once the certificate exists, the Ingress was updated to:

- Listen on both port 80 and port 443
- Redirect HTTP to HTTPS
- Attach the ACM certificate ARN via annotation

```yaml
alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
alb.ingress.kubernetes.io/ssl-redirect: '443'
alb.ingress.kubernetes.io/certificate-arn: <certificate_arn>
```

The old Ingress (HTTP only) was destroyed and a new one was created with the updated config.

---

### 5. Route 53 Domain Mapping

After the ALB is created, a Route 53 alias record is created to point the subdomain to the ALB DNS name:

```hcl
resource "aws_route53_record" "app" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "app.${var.domain_name}"
  type    = "A"

  alias {
    name                   = <ingress_hostname>
    zone_id                = <alb_hosted_zone_id>
    evaluate_target_health = true
  }
}
```

The `ingress_hostname` is pulled from the Kubernetes Ingress resource output — Terraform automatically chains the two.

---

### 6. Wildcard Certificates and Wildcard DNS Records

When multiple subdomains are needed (app, ArgoCD, Grafana, Prometheus), creating a separate certificate for each is wasteful.

**Solution: Wildcard certificate**

```hcl
resource "aws_acm_certificate" "wildcard" {
  domain_name = "*.${var.domain_name}"
  validation_method = "DNS"
}
```

A single wildcard cert covers `app.domain.com`, `argocd.domain.com`, `grafana.domain.com`, etc.

**Matching wildcard Route 53 record:**

```hcl
resource "aws_route53_record" "wildcard" {
  name = "*.${var.domain_name}"
  type = "A"
  ...
}
```

- Route 53 resolves any subdomain to the ALB
- The ALB uses **Ingress rules** (host headers) to route to the correct service
- DNS does the "who" — ALB does the "where"

---

### 7. Shared ALB with Ingress Groups

By default, each Ingress creates a separate ALB. For multiple applications (app, ArgoCD, Grafana) sharing one ALB, use the `group.name` annotation:

```yaml
alb.ingress.kubernetes.io/group.name: "shared-alb"
```

Any Ingress with the same group name shares the same ALB. The controller merges all routing rules into a single ALB automatically.

**Why this matters:** ALBs are charged per hour. 5 services × 5 ALBs = unnecessary cost and complexity. One shared ALB handles everything.

---

### 8. ArgoCD — Helm Chart Deployment via Terraform

ArgoCD was deployed as a Helm chart using the Terraform `helm_release` resource, following the same pattern as the AWS Load Balancer Controller:

- Create namespace: `argocd`
- Deploy the official ArgoCD Helm chart
- Configure an Ingress with the shared ALB group and wildcard certificate so ArgoCD is accessible at `argocd.domain.com`

**Key point:** ArgoCD is itself a CRD-based application. It ships with custom Kubernetes resource types (`Application`, `AppProject`, etc.). When you install ArgoCD, you are installing both the controller and the CRD definitions.

---

### 9. EBS CSI Driver Add-on

To allow Prometheus (StatefulSet) and Grafana to use persistent volumes on EKS, the **Amazon EBS CSI driver** must be installed as an EKS add-on.

- Without it, PVC provisioning fails — the cluster has no storage class that can dynamically provision EBS volumes
- After installing the add-on, a `gp2` storage class appears in the cluster automatically
- A matching IAM role is needed for the CSI driver, following the same OIDC pattern as the load balancer controller

---

### 10. Prometheus and Grafana — Helm Chart Deployment

Deployed via the `kube-prometheus-stack` Helm chart with Terraform:

- **Prometheus** runs as a StatefulSet and needs a PVC (`storageClassName: gp2`, `20Gi`)
- **Grafana** runs as a Deployment, needs a PVC (`10Gi`), and gets an Ingress at `grafana.domain.com`
- Admin password is set in the values — will be moved to AWS Secrets Manager in a future class
- Alert Manager is disabled for now — alerting will be configured via Grafana directly
- Both use the shared ALB group and wildcard certificate

---

### 11. Repository and Access Control Structure

**How infra is separated from application code:**

| Repository | Owned by | Contains |
|---|---|---|
| `infra-eks` | DevOps team | EKS cluster, add-ons, networking, IAM |
| `infra-tools` | DevOps team | ArgoCD, Prometheus, Grafana, cert setup |
| `app-k8s` | Shared (DevOps + App team) | Kubernetes manifests or Helm values for the app |
| `app-code` | Developer team | Application source code, Dockerfile |

Developers do not have direct access to the EKS cluster. They push code; ArgoCD handles deployment. DevOps manages everything below the application layer.

---

### 12. DB Migration Jobs

The current setup runs migrations inside the application container on startup. The correct pattern is a **Kubernetes Job**:

- A Job runs once, completes, and exits
- The migration script is already in the Docker image (copied in the Dockerfile)
- The Job should run before the main Deployment starts
- In CI/CD, the migration job runs as part of the pipeline before the new image is deployed
- This will be implemented in an upcoming class

---

## Key Discussion Points

- `kubectl rollout restart` is the fix when a pod needs to pick up a new IAM role — no config changes needed
- Pod IPs are registered in ALB target groups directly; the ingress controller handles registration/deregistration automatically when pods change
- Wildcard `*.domain.com` in Route 53 resolves all subdomains to the same ALB; host-based routing in the ALB then directs traffic to the right service
- You can use the same ALB for internal tools (ArgoCD, Grafana) and external apps by controlling access at the network policy or WAF level — it is a cost vs. isolation tradeoff
- For authentication on ArgoCD and Grafana dashboards in production: use SSO (Okta, Azure AD) rather than local username/password; MFA is enforced at the SSO provider level, not at the tool level
- Helm charts vs. manifest files: both are supported by ArgoCD; the preference is Helm for packaging, but manifest files are fine for simple or legacy setups
- Multiple microservices can each have their own Helm chart, or all share one chart with separate value files — both patterns are used in production

---

## Exercise / Homework

1. **Fix your setup from last class** — if the load balancer controller was failing, restart the pods:
   ```bash
   kubectl rollout restart deployment aws-load-balancer-controller -n kube-system
   ```
   Verify it comes up healthy with `kubectl get pods -n kube-system`.

2. **Deploy ingress with HTTPS via Terraform** — use the code from class to:
   - Request an ACM certificate for your subdomain
   - Create the DNS validation record
   - Update the Ingress to use port 443 with the certificate ARN
   - Create the Route 53 alias record pointing to the ALB

3. **Add the shared ALB group annotation** to your Ingress and test that it works correctly.

4. **Deploy ArgoCD** using the Terraform Helm chart code. Once deployed, port-forward the service and verify you can reach the UI:
   ```bash
   kubectl port-forward svc/argocd-server -n argocd 8080:443
   ```

5. **Enable the EBS CSI driver** on your cluster and verify a `gp2` storage class appears:
   ```bash
   kubectl get storageclass
   ```

6. **Read about the App of Apps pattern** in ArgoCD — this will be used in the next class for managing multiple application deployments.

---

## What's Next

- CI/CD pipeline with OIDC (replace hardcoded AWS credentials in GitHub Actions)
- ArgoCD connected to the application repository — full GitOps deployment demo
- Prometheus and Grafana are fully wired up with dashboards
- DB migration Jobs implemented in the pipeline
- Secrets management — moving credentials from Terraform variables to AWS Secrets Manager
- Then: microservices deployment with StatefulSets, network policies, service mesh concepts
