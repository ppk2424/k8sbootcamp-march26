# fork https://github.com/akhileshmishrabiz/k8sbootcamp-march26
# then clone your repo in laptop



# make sure Terraform installed
# use tfenv to fix terraform version to 1.12.1 

# aws creds configures
aws configure 


# EKS infra deploy
```bash
cd eks/eks-infra
# update your bavckend
# make sure terraorm version matches to tf files in versions.tf 
# if you dont have, use the latest version of terraform and update versions.tf
terraform init
terraform
terraform apply

```

# list cluster
```bash
aws eks list-clusters --region ap-south-1
```

# update the kubeconfig so you can run kubectl
```bash
# install kubectl (google steps)
# configure the kubeconfig

aws eks update-kubeconfig --name eks-cluster --region ap-south-1
kubectl config get-contexts
kubectl config rename-context arn:aws:eks:ap-south-1:879381241087:cluster/eks-cluster eks-cluster
kubectl config get-contexts

```

# ecr repo 
```bash
aws ecr create-repository --repository-name ecommerce-product-service --region ap-south-1
aws ecr create-repository --repository-name ecommerce-user-service --region ap-south-1
aws ecr create-repository --repository-name ecommerce-cart-service --region ap-south-1
aws ecr create-repository --repository-name ecommerce-order-service --region ap-south-1
aws ecr create-repository --repository-name ecommerce-payment-service --region ap-south-1
aws ecr create-repository --repository-name ecommerce-notification-service --region ap-south-1
aws ecr create-repository --repository-name ecommerce-api-gateway --region ap-south-1
aws ecr create-repository --repository-name ecommerce-frontend --region ap-south-1
aws ecr create-repository --repository-name ecommerce-seed --region ap-south-1

```

# deploy aws load balancer controller

``` bash
cd eks/k8s-services/aws-load-balancer-controller

# update backed, providers region, bucket and all
terraform init
terraform apply

# you shoudl see aws-load-balancer-controller pods in kube-system folder
```

## argocd
```
cd eks/k8s-services/argocd

# update backed, providers region, bucket and all
terraform init
terraform apply
```

# logging/monitoring
``` bash
cd eks/k8s-services/logging-monitoring
# update versions ,providers and 
terraform apply
```

# vault 
```bash

cd eks/k8s-services/vault-eso
terraform apply

```

# now the app related stuff deployment

# CNPG operators
```bash 

cd eks-microservice-implementation
cd infra/cnpg-operator
terraform apply --auto-approve
```

# vault-secrets

```bash
cd eks-microservice-implementation
cd infra/vault-secrets 


```