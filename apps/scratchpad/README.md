# Scratchpad

Pod Debian persistant servant d'environnement de travail interactif : accès au
datalake, outils data préinstallés (Node.js, pnpm, uv, awscli, filebeat, jq,
tmux, parallel), volume de stockage important.

## Installation

```bash
kubectl apply -f persistent-volume-claim.yaml
kubectl apply -f deployment.yaml
```

## Provisionnement des outils

Une fois le pod démarré, exécuter [`install.sh`](install.sh) à l'intérieur :

```bash
kubectl exec -it debian-deployment -- bash -c "$(cat install.sh)"
```

## Accès

```bash
kubectl exec -it debian-deployment -- bash
```
