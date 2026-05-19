# Runbook — Rook-Ceph

Installation, opération et désinstallation d'un cluster Ceph distribué via
l'opérateur Rook 1.16.

## Installation de l'opérateur

```bash
kubectl create -f crds.yaml -f common.yaml -f operator.yaml
```

Attendre que l'opérateur et les services de discovery soient déployés :

```bash
kubectl -n rook-ceph get pod
```

Sortie attendue (extrait) :

```text
NAME                                  READY   STATUS    RESTARTS   AGE
rook-ceph-operator-65b89665df-n2s8g   1/1     Running   0          74s
rook-discover-7psxb                   1/1     Running   0          53s
```

## Création du cluster

```bash
kubectl create -f cluster.yaml
```

S'ajoutent alors des pods pour le FS et le RBD par nœud, des provisioners, les
`ceph-mon` et `ceph-mgr`, les crashcollector et les exporter, ainsi qu'un OSD
par disque. Attendre que tous les OSD soient `Running` :

```bash
kubectl -n rook-ceph get pod
```

## Toolbox

```bash
kubectl create -f toolbox.yaml
kubectl -n rook-ceph exec -it deploy/rook-ceph-tools -- bash
```

À l'intérieur :

```bash
ceph status
ceph osd status
ceph df
rados df
```

> Environ 4,3 % du stockage est utilisé par des métadonnées sur les disques.

Quand l'inspection est terminée :

```bash
kubectl -n rook-ceph delete deploy/rook-ceph-tools
```

## Classes de stockage

> ⚠️ La première classe créée doit être la classe par défaut, sinon les volumes
> persistants ne seront pas créés.

### Bloc

```bash
kubectl apply -f storageClass/block-replicated.yaml
```

### Objet (datalake)

```bash
kubectl apply -f storageClass/datalake/datalake-ec.yaml
kubectl apply -f storageClass/datalake/storage-class.yaml
kubectl apply -f storageClass/datalake/object-bucket-claim-gdelt.yaml
```

Voir [`storageClass/datalake/README.md`](storageClass/datalake/README.md) pour
le détail des claims et l'extraction des credentials.

## Tailscale operator

```bash
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update
export $(grep -v '^#' .env | xargs)
helm upgrade \
  --install tailscale-operator tailscale/tailscale-operator \
  --namespace tailscale --create-namespace \
  --set-string oauth.clientId="${clientID}" \
  --set-string oauth.clientSecret="${clientSecret}" \
  --wait
```

## Récupérer les clefs d'un object store

```bash
kubectl -n default get secret datalake \
  -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 --decode
kubectl -n default get secret ceph-bucket \
  -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 --decode
```

## Désinstallation

Supprimer les pools et storage classes :

```bash
kubectl delete -n rook-ceph cephblockpools.ceph.rook.io rook-ceph-block-pool
kubectl delete storageclasses.storage.k8s.io rook-ceph-block
kubectl delete -n rook-ceph cephblockpools.ceph.rook.io rook-ceph-block-replicated-pool
kubectl delete storageclasses.storage.k8s.io rook-ceph-block-replicated
```

Détruire le cluster Ceph :

```bash
kubectl -n rook-ceph patch cephcluster rook-ceph --type merge \
  -p '{"spec":{"cleanupPolicy":{"confirmation":"yes-really-destroy-data"}}}'
kubectl -n rook-ceph delete cephcluster rook-ceph
kubectl -n rook-ceph get cephcluster
```

Une fois les cleanup pods passés :

```bash
kubectl delete -f operator.yaml
kubectl delete -f common.yaml
kubectl delete -f crds.yaml
```

Enfin, supprimer les données sur les disques avec [`cleanup.sh`](cleanup.sh).
Vérifier sur tous les nœuds :

```bash
lsblk -f
```
