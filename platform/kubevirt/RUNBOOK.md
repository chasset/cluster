# Runbook — KubeVirt

Installation de l'opérateur KubeVirt et de la CR qui déploie les composants
nécessaires à l'exécution de machines virtuelles dans le cluster.

## Installation

Repérer la dernière release :

```bash
curl https://storage.googleapis.com/kubevirt-prow/release/kubevirt/kubevirt/stable.txt
```

Déployer l'opérateur KubeVirt :

```bash
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.3.1/kubevirt-operator.yaml
```

Créer la CR KubeVirt (qui déclenche l'installation des composants) :

```bash
kubectl apply -f https://github.com/kubevirt/kubevirt/releases/download/v1.3.1/kubevirt-cr.yaml
```

Attendre que tous les composants soient disponibles :

```bash
kubectl -n kubevirt wait kv kubevirt --for condition=Available
```
