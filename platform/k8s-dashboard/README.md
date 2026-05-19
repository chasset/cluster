# Kubernetes Dashboard

Déploiement du dashboard officiel Kubernetes via Helm, avec un compte de service
`admin-user` pour l'authentification.

## Installation

```bash
./manage.sh
kubectl apply -f service-account.yaml
kubectl apply -f cluster-role-binding.yaml
kubectl apply -f bearer-token.yaml
```

## Récupérer le token d'admin

```bash
./credentials.sh
```
