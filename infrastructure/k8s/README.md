# Kubernetes manifests (scaffold)

These manifests are a **documented starting point**, not a turnkey production
deployment. They show the intended shape: a non-root, probed, resource-bounded
backend Deployment driven by a ConfigMap + Secret, fronted by a Service.

Out of scope here (and deliberately left to your platform/GitOps tooling):
Ingress/TLS, HorizontalPodAutoscaler, NetworkPolicies, PodDisruptionBudgets,
the Temporal cluster, managed Postgres (with pgvector) and Redis, MinIO/S3, and
the Keycloak deployment. See `docs/deployment.md` for the full checklist.

Apply order (once secrets are provisioned securely):

    kubectl apply -f namespace.yaml
    kubectl apply -f configmap.yaml
    kubectl apply -f secret.example.yaml   # replace with real secret source
    kubectl apply -f backend-deployment.yaml
    kubectl apply -f backend-service.yaml
