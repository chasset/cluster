# RStudio

Déploiement d'un RStudio Server dans le cluster, avec un volume persistant pour
le workspace utilisateur.

## Installation

```bash
kubectl apply -f namespace.yaml
kubectl apply -f persistent-volume-claim.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```
