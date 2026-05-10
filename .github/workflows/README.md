# E-commerce CI/CD Setup Steps

## 1. Create ECR Repositories

Created 8 ECR repositories in `ap-south-1` region for all microservices:

```bash
for repo in ecommerce-product-service ecommerce-user-service ecommerce-cart-service ecommerce-order-service ecommerce-payment-service ecommerce-notification-service ecommerce-api-gateway ecommerce-frontend; do
  aws ecr create-repository \
    --repository-name "$repo" \
    --region ap-south-1 \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE
done
```

**Repositories created:**
- `ecommerce-product-service`
- `ecommerce-user-service`
- `ecommerce-cart-service`
- `ecommerce-order-service`
- `ecommerce-payment-service`
- `ecommerce-notification-service`
- `ecommerce-api-gateway`
- `ecommerce-frontend`

**ECR Registry:** `879381241087.dkr.ecr.ap-south-1.amazonaws.com`
