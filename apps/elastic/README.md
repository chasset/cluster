# Elasticsearch

Déploiement d'Elasticsearch via l'opérateur
[ECK](https://www.elastic.co/guide/en/cloud-on-k8s/current/).

## Prérequis

L'opérateur ECK n'est à installer qu'une seule fois pour tout le cluster :

```bash
./operator.sh
```

## Installation

Cluster par défaut (10 nœuds, version `quickstart`) :

```bash
kubectl apply -f cluster.yaml
```

Variante grande échelle (50 nœuds) :

```bash
kubectl apply -f cluster-50.yaml
```
