# JupyterHub

Déploiement de JupyterHub via le Helm chart officiel
[zero-to-jupyterhub-k8s](https://hub.jupyter.org/helm-chart/).

Les valeurs Helm sont dans [`config.yaml`](config.yaml).

## Prérequis

```bash
helm repo add jupyterhub https://hub.jupyter.org/helm-chart/
helm repo update
```

## Installation

```bash
helm upgrade --cleanup-on-fail --install jupyter jupyterhub/jupyterhub \
  --namespace jupyter --create-namespace \
  --version=4.2.0 \
  --values config.yaml
```

## Désinstallation

```bash
helm uninstall jupyter --namespace jupyter
kubectl delete namespace jupyter
```
