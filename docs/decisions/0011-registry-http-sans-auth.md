# 0011 — Registry interne HTTP sans authentification

## Contexte

Le cluster héberge un container registry interne
([distribution v3](https://github.com/distribution/distribution),
[`platform/container-registry/`](../../platform/container-registry/)) pour
stocker les images des chercheurs et builds maison. Deux questions :

1. **TLS ou HTTP clair ?**
2. **Authentification (htpasswd / token) ou anonyme ?**

Le périmètre d'accès est :

- intra-cluster : pulls par `kubelet` depuis le réseau pods Cilium
  (`10.244.0.0/16`) ;
- accès distant : le registry n'est exposé que sur le réseau cluster — l'accès
  se fait par `kubectl port-forward` ou par un saut sur un nœud du cluster.

## Décision

**HTTP en clair, pas d'authentification**. Le Service expose le registry sur le
port 80, et aucun module `REGISTRY_AUTH` n'est activé.

La sécurité de l'accès est **déléguée au contrôle d'accès au Service** :

- intra-cluster, les pods qui peuvent résoudre `registry.registry:80` sont de
  confiance par hypothèse (mono-tenant) ;
- pour l'accès distant, l'accès passe par `kubectl port-forward` ou par un saut
  SSH sur un nœud.

C'est cohérent avec
[`0003-pas-de-chiffrement-ceph-tailscale.md`](0003-pas-de-chiffrement-ceph-tailscale.md)
: la sécurité repose sur le contrôle d'accès au réseau privé, pas sur un tunnel
d'accès distant.

## Statut

Accepted (2026-05-28).

## Conséquences

**Bénéfices.**

- Zéro friction de configuration : pas de cert à provisionner ni de htpasswd à
  maintenir.
- Push/pull triviaux depuis tout poste joignant le Service (via port-forward)
  (`docker push registry:80/...` avec `insecure-registries`).
- Cohérence avec le reste du cluster (Ceph RGW, etc.) — un seul modèle de
  sécurité réseau à comprendre.

**Coûts assumés.**

- **Tout client autorisé à atteindre le Service peut pusher** des images
  arbitraires, y compris écraser des tags existants. L'accès est limité aux pods
  du cluster + aux opérateurs via `kubectl port-forward`.
- **Tout pod du cluster peut tirer** depuis le registry (pas de
  `imagePullSecret` requis). Acceptable pour un cluster mono-tenant ;
  inacceptable si on introduit du multi-tenancy.
- **`docker push` en HTTP** : exige `"insecure-registries": ["registry:80"]` sur
  chaque daemon Docker client. Documenté dans
  [`platform/container-registry/README.md`](../../platform/container-registry/README.md).

**Cas où cette décision est à revoir.**

- Si le cluster expose des services à des utilisateurs hors équipe d'opération
  (étudiants, équipes externes) → activer htpasswd ou OIDC (token-based auth de
  distribution).
- Si on passe en multi-tenants → introduire des `imagePullSecrets` par
  namespace + ACL côté registry.
- Si le registry est exposé en accès public (au-delà du port-forward) → TLS
  obligatoire (cert-manager + Let's Encrypt) + authentification.
