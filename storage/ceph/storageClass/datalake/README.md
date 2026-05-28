# Datalake — Object Store

Object store Ceph compatible S3, exposé via RGW (Rados Gateway). Sert de
datalake pour les sources de données ingérées par le cluster.

> ⚠️ **Comportement destructif** : `preservePoolsOnDelete: false` (cf.
> [`datalake-ec.yaml:21`](datalake-ec.yaml#L21)) signifie que **supprimer le
> `CephObjectStore` détruit aussi les pools `datalake.rgw.buckets.data` et
> `datalake.rgw.buckets.index`** — donc **toutes les données et buckets** S3.
> Décision assumée pour ce datalake de recherche (ré-ingestible depuis les
> sources upstream). Pour conserver les pools, passer à
> `preservePoolsOnDelete: true` **avant** toute suppression.

## Installation

```bash
kubectl apply -f datalake-ec.yaml
kubectl apply -f storage-class.yaml
```

Pour exposer le service via Tailscale (**si le Tailscale operator est
déployé**), annoter le service `rook-ceph-rgw-datalake` créé automatiquement :

```yaml
metadata:
  annotations:
    tailscale.com/expose: 'true'
    tailscale.com/hostname: datalake
```

Sans Tailscale, le service reste accessible depuis l'intérieur du cluster
(`rook-ceph-rgw-datalake.rook-ceph:80`) ou via
`kubectl -n rook-ceph port-forward svc/rook-ceph-rgw-datalake 8080:80`.

## Créer une bucket

Créer un fichier de claim (voir
[`object-bucket-claim-gdelt.yaml`](object-bucket-claim-gdelt.yaml) pour un
exemple), puis l'appliquer.

Récupérer les credentials :

```bash
BUCKET=stormglass
kubectl get secret "${BUCKET}" -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 --decode
echo
kubectl get secret "${BUCKET}" -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 --decode
echo
```

## Utilisateur global

Après création d'un utilisateur (voir [`user.yaml`](user.yaml) ou
[`user-datalake.yaml`](user-datalake.yaml)), celui-ci accède à tout l'object
store :

```bash
USER=rook-ceph-object-user-datalake-admin
kubectl -n rook-ceph get secret "${USER}" -o jsonpath='{.data.AccessKey}' | base64 --decode
echo
kubectl -n rook-ceph get secret "${USER}" -o jsonpath='{.data.SecretKey}' | base64 --decode
echo
```
