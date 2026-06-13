# RStudio

Déploiement d'un RStudio Server (image `rocker/geospatial:4.6.0`) avec un volume
persistant 1 Ti pour le workspace utilisateur, sur la StorageClass par défaut
(`rook-ceph-block-replicated`, réplicat ×3).

## Décision assumée

**Pas d'authentification** (`DISABLE_AUTH=true`). Quiconque atteint `rstudio:80`
ouvre directement une session — shell + filesystem. La sécurité repose sur le
contrôle d'accès au Service (réseau interne, accès à l'API Kubernetes restreint
aux postes autorisés).

Voir
[`docs/decisions/0012-rstudio-disable-auth.md`](../../docs/decisions/0012-rstudio-disable-auth.md)
pour le contexte complet et les garde-fous opérationnels.

> ⚠️ Cette ADR devient caduque dès qu'on ouvre l'instance à plus d'une équipe de
> confiance ou à des utilisateurs externes. Y revenir avant tout élargissement
> du périmètre d'accès.

**SPOF applicatif assumé** (audit P8) : `replicas: 1` sur PVC RBD
(`ReadWriteOnce`) → pas de scale-out, et la perte du nœud hébergeant le pod rend
RStudio indisponible le temps que Kubernetes le replanifie ailleurs et
**rattache le volume RBD** (quelques minutes ; les données survivent, réplicat
×3). Acceptable pour un usage recherche mono-utilisateur. HA réelle = bascule
sur CephFS (`ReadWriteMany`) + plusieurs replicas, hors périmètre actuel.

## Installation

```bash
kubectl apply -f namespace.yaml
kubectl apply -f persistent-volume-claim.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

## Vérification

```bash
kubectl -n rstudio get pods,pvc,svc                  # tout Ready, PVC Bound
```

## Accès

Depuis un poste autorisé à parler à l'API Kubernetes :
`kubectl -n rstudio port-forward svc/rstudio-service 8787:80`, puis ouvrir
`http://localhost:8787`.

Pas d'écran de login : vous arrivez directement sur l'IDE en tant qu'utilisateur
`rstudio`.

## Désinstallation

```bash
kubectl delete -f service.yaml
kubectl delete -f deployment.yaml
kubectl delete -f persistent-volume-claim.yaml   # ⚠️ supprime le workspace
kubectl delete -f namespace.yaml
```
