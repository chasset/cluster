# Container registry

Déploiement d'un container registry interne au cluster (image officielle
`registry:2`), avec un volume persistant pour les blobs.

> ⚠️ Le registre est exposé en HTTP. Pour pusher/puller des images, tagger en
> `registry:80/...` et configurer le démon Docker :
>
> ```json
> {
>   "insecure-registries": ["registry:80"]
> }
> ```

## Installation

```bash
kubectl apply -f namespace.yaml
kubectl apply -f persistent-volume-claim.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```
