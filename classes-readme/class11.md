# Class Notes — May 3, 2026
## LivingDevOps Bootcamp · Session 11

> **Note:** The previous class (Session 10 / May 2) recording was not captured. Refer to the three CI/CD pipeline files in the repository and use Claude or ChatGPT to understand them. Akhilesh will revisit any gaps next class.

---

## Topics Covered

### 1. Recap — What Was Built Last Class (No Recording)

Three GitHub Actions workflows were built:

1. **Image build pipeline** — builds and pushes backend and frontend Docker images to ECR
2. **PR check pipeline** — runs Trivy security scans on images; blocks merges to `main` if critical/high CVEs are found
3. **Terraform deployment pipeline** — manual trigger, accepts `apply` or `destroy` input plus a path, and runs Terraform for EKS infra, load balancer controller, ArgoCD setup, or logging/monitoring setup in sequence (infra must run first)

ArgoCD deployment integration was **not** covered yet — coming next week.

---

### 2. Why Static AWS Credentials in GitHub Secrets Are a Problem

Storing `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as long-lived GitHub secrets is risky:

- Credentials never auto-expire
- If leaked, an attacker has persistent AWS access
- Rotation is manual and often skipped
- Not the production standard

The solution is **OIDC** — no stored credentials at all.

---

### 3. GitHub Actions OIDC with AWS

**What OIDC does here:** It creates a trust relationship between GitHub Actions and AWS so that a workflow can request a short-lived token at runtime instead of using stored keys.

#### How it works — two questions to answer

| Question | Concept | Detail |
|---|---|---|
| **Who** is making the request? | `sub` (subject) | GitHub repo + branch (e.g. `repo:org/repo:ref:refs/heads/main`) |
| **What** can they do? | `aud` (audience) | `sts.amazonaws.com` — they can assume an IAM role |

#### Setup steps

1. **Create an OIDC Identity Provider** in AWS IAM  
   URL: `https://token.actions.githubusercontent.com`  
   Client ID: `sts.amazonaws.com`

2. **Create an IAM Role** with a trust policy that:
   - Allows `sts:AssumeRoleWithWebIdentity`
   - Restricts `sub` to specific repo + branch combinations
   - Sets `aud` to `sts.amazonaws.com`

3. **Attach an IAM Policy** to the role (ECR push, or AdminAccess for full pipeline use)

4. **Update the GitHub Actions workflow** — replace the credentials step with:
   ```yaml
   - uses: aws-actions/configure-aws-credentials@v4
     with:
       role-to-assume: arn:aws:iam::ACCOUNT_ID:role/ROLE_NAME
       aws-region: ap-south-1
   ```

#### Why lock down to specific repos and branches

- If you wildcard all repos in your org, any compromised or rogue repository gets full AWS access
- Production standard: one role per purpose, locked to the exact repo and branch that needs it
- Multiple conditions (multiple repos/branches) are added as separate `StringLike` conditions in the trust policy — not by adding to the same condition string

---

### 4. STS — Security Token Service

`sts.amazonaws.com` appears in both `aud` and the trust policy — here is what it means:

- STS is the AWS service that issues **temporary credentials**
- When GitHub Actions assumes a role via OIDC, STS generates a short-lived token for that session
- The same mechanism is used when EC2 instances or EKS pods assume roles — STS issues the token in the background
- "Assuming a role" = putting on a hat with specific permissions; STS is the mechanism that gives you the hat

---

### 5. Terraform for OIDC Setup

The OIDC configuration was moved from manual console clicks to Terraform (`aws-github-oidc-terraform/main.tf`).

Key resources:

```hcl
# 1. Create the OIDC provider (one per AWS account)
resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# 2. Create the IAM role with trust policy
resource "aws_iam_role" "aws-github-oidc-march26" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.github_actions.arn }
      Condition = {
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:ORG/REPO:ref:refs/heads/main"
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

# 3. Attach permissions to the role
resource "aws_iam_role_policy_attachment" "attach_ecr_policy" {
  role       = aws_iam_role.aws-github-oidc-march26.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
```

**Dynamic multi-repo mapping:** The `locals` block holds a list of `{ user, repo, branch }` objects. Terraform iterates over them to generate the `StringLike` condition entries — no need to manually duplicate the trust policy for each repo.

---

### 6. Trivy Security Scans and Fixing Vulnerabilities

When a Trivy scan fails in the PR check pipeline:

- Read the output — it identifies the exact CVE, severity, and the affected package
- Vulnerabilities come from three places: the **base image**, **system packages** in the Dockerfile, or **application dependencies** (npm, pip, go modules)
- Fixing approach: update the base image to a newer version, upgrade the affected package, or pin the dependency to a patched version
- Downgrading is not always the fix — sometimes a patched version is a higher version
- Best way to learn: run the scan, see what breaks, fix it, and you will have a real answer for interviews

---

### 7. Helm Charts — Introduction

A Helm chart is a way to **package a Kubernetes application** so you do not manage 20 separate manifest files.

#### Structure

```
my-chart/
  Chart.yaml        # chart name, chart version, app version
  values.yaml       # all configurable values in one place
  templates/        # deployment, service, ingress, etc. — with dynamic placeholders
```

#### How values flow

In `values.yaml`:
```yaml
backend:
  image:
    repository: 123456789.dkr.ecr.ap-south-1.amazonaws.com/backend
    tag: "abc123"
```

In `templates/deployment.yaml`:
```yaml
image: "{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}"
```

#### Key commands

```bash
helm create my-chart          # scaffold chart structure
helm lint ./my-chart          # validate the chart
helm install myapp ./my-chart # deploy to Kubernetes
helm upgrade myapp ./my-chart # apply changes
helm rollback myapp 1         # roll back to revision 1
```

#### In production

- The **chart** (templates + Chart.yaml) is built once and pushed to ECR as an OCI artifact
- The **values file** lives in Git — this is what ArgoCD watches
- When the image tag changes in `values.yaml`, ArgoCD detects it and redeploys
- Nobody writes Helm charts manually anymore — use AI to generate the templates, then review and adjust

---

### 8. Helm Charts vs. Manifest Files vs. Kustomize

| Approach | Use Case |
|---|---|
| Raw manifests | Learning, very small apps — not recommended for production |
| Helm chart | Package once, reuse across environments with different values |
| Kustomize | Overlay-based customization without templating; good for patching existing charts |

Helm chart is preferred for packaging your own application. ArgoCD supports all three — point it to the path or the chart.

---

### 9. ArgoCD Overview (Conceptual)

ArgoCD is a GitOps CD tool. It watches a Git repo and keeps the cluster in sync with what Git says.

**How the full pipeline works:**

```
Code change → GitHub Actions builds image → pushes to ECR
           → GitHub Actions updates image tag in values.yaml on a branch
           → ArgoCD detects the change → deploys the new version to the cluster
```

**Environments via branches:**

- `argocd-dev` branch → ArgoCD for dev cluster watches this branch
- `argocd-prod` branch → ArgoCD for prod cluster watches this branch
- GitHub Actions promotes changes by committing the new tag to the right branch

**App of Apps pattern** — read about this before next class. It is a way to manage multiple ArgoCD applications from a single parent application.

---

### 10. Secrets Management — The Right Way

| Method | Use Case |
|---|---|
| GitHub Secrets | CI/CD credentials only (the AWS role ARN, ECR region) — not application secrets |
| AWS Secrets Manager | Application secrets (DB passwords, API keys) pulled at runtime |
| OIDC → Secrets Manager | GitHub Actions authenticates via OIDC, then pulls secrets from Secrets Manager at pipeline time |
| External Secrets Operator | Syncs secrets from Secrets Manager into Kubernetes Secrets at cluster level |

The flow: GitHub Actions uses OIDC to authenticate → fetches secrets from Secrets Manager → injects into the pipeline or into the cluster. No long-lived credentials stored anywhere.

---

### 11. Trusting Open Source Operators and Packages

When using publicly available operators (CloudNativePG, etc.):

- Check who maintains it — look for known organisations, AWS, CNCF, etc.
- Check adoption — star count, contributor activity, production case studies
- Check CVEs and release cadence
- Supply chain risk is real — any dependency in your app could be compromised (this is why Trivy scans matter)
- Industry standard tools that have been widely adopted are generally safe to use; obscure packages with few contributors are not

---

## Key Discussion Points

- One OIDC provider per AWS account is enough; multiple roles with different trust conditions handle different repos/teams
- `aud = sts.amazonaws.com` means "this token can be used to assume an AWS role via STS" — it does not change between repos
- `sub` is what changes per repo and branch combination
- Helm chart versioning: update `appVersion` when the application changes, update `version` when the chart structure changes
- ECR supports OCI artifacts — Helm charts can be stored and pulled from ECR just like container images
- ArgoCD is not just for image changes — it reconciles the full desired state in Git against the live cluster state (deleted deployments get recreated, drift gets corrected)
- The difference between Helm (package manager) and ArgoCD (CD controller) — Helm installs, ArgoCD watches and continuously reconciles
- Storing Helm charts in ECR vs GitHub: access control, separation of concerns, no code mixed with packaging artifacts

---

## Exercise / Homework

1. **Study the pipelines** — go through the three workflow files in the repository. Use Claude or ChatGPT to understand each step. Note any questions for next class.

2. **Set up OIDC manually** (for understanding):
   - Go to AWS IAM → Identity Providers → Add Provider
   - Use `https://token.actions.githubusercontent.com` as the URL
   - Create an IAM role with a trust policy pointing to your GitHub user + a test repo + `main` branch
   - Attach ECR push permissions or AdministratorAccess

3. **Apply the Terraform OIDC code** — use `aws-github-oidc-terraform/main.tf` and apply it from your local machine. Verify the role and identity provider appear in AWS IAM.

4. **Run a Trivy scan locally:**
   ```bash
   trivy image <your-image>:<tag>
   ```
   See what comes back. Try to identify which CVEs are from the base image vs. your app packages.

5. **Create a Helm chart** for the three-tier app from the earlier sessions:
   ```bash
   helm create three-tier-app
   ```
   Move your deployment, service, and configmap manifests into `templates/`. Extract image names and tags into `values.yaml`. Run `helm lint` to check it.

6. **Read about App of Apps in ArgoCD** — this will be used next class. Understand the concept before the demo.

---

## What's Next

- **Live demo:** Deploying the e-commerce microservices app on Kind using Helm charts
- **ArgoCD setup** and connecting it to the repository
- **App of Apps** implementation
- **Secrets management** — External Secrets Operator pulling from AWS Secrets Manager into Kubernetes
- At least two additional classes have been added to the schedule to cover the remaining topics properly

---

*Catch up on all previous sessions before next class — next week will be heavily hands-on with fewer pauses for questions mid-session.*
