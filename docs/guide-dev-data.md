# Guide du développeur data — consommer la plateforme

Ce guide s'adresse au **développeur data** qui écrit du code (pipelines, jobs,
requêtes) consommant les briques de la plateforme. Il décrit le **contrat
d'interface** : quels services joindre, avec quels secrets, quel paramétrage.

> **Frontière (ADR [0022](decisions/0022-argocd-gitops-applicatif.md) /
> [0023](decisions/0023-plateforme-exemple-generique.md)).** Ce dépôt décrit
> l'**infrastructure** (générique). Le **code métier** (assets, pipelines,
> requêtes réelles) vit dans le dépôt applicatif (`atlas`), pas ici. Les
> exemples ci-dessous sont **génériques et jetables** — ils montrent le _comment
> se brancher_, pas la logique d'un projet. Les valeurs réelles (mots de passe,
> hostnames) viennent d'une config locale non versionnée.

Ce guide est orienté _usage_. Pour _ce que fait_ chaque technologie
(PostgreSQL/CloudNativePG, Dagster, Marquez, Argo CD, Gitea, Ceph, Cilium…) et
_pourquoi elle est là_, voir
[Composants — la pile technologique](composants.md).

Toutes les adresses sont des **services Kubernetes intra-cluster** (DNS
`*.svc.cluster.local`) : votre code tourne **dans un pod du cluster**, dans un
namespace autorisé par les NetworkPolicies (cf. chaque brique).

> **Vous travaillez en local ?** Sur un banc Lima (topologie `multi-node-3`,
> chemin `atlas`), les adresses `*.svc.cluster.local` ne sont **pas** joignables
> depuis votre poste, et les URLs `*.cluster.lan` ne **résolvent pas** (ce sont
> des placeholders, cf. plus bas). Pour atteindre les UIs et **pousser sur
> Gitea** depuis votre machine, voir
> [Travailler en local sur le banc multi-node-3 (chemin atlas)](#travailler-en-local-sur-le-banc-multi-node-3-chemin-atlas).

## Vue d'ensemble des points d'accès

| Brique               | Service (intra-cluster)                      | Port | Auth (Secret)                        |
| -------------------- | -------------------------------------------- | ---- | ------------------------------------ |
| PostgreSQL (CNPG)    | `pg-rw.postgres.svc.cluster.local` (primary) | 5432 | Secret du rôle (`pg-role-<rôle>`)    |
| PostgreSQL (replica) | `pg-ro.postgres.svc.cluster.local` (lecture) | 5432 | idem                                 |
| Marquez (lineage)    | `marquez.marquez.svc.cluster.local`          | 5000 | aucune (intra-cluster)               |
| Registry d'images    | `registry:80` (sur les nœuds)                | 80   | aucune (HTTP interne, ADR 0011)      |
| S3 datalake (RGW)    | `rook-ceph-rgw-datalake.rook-ceph`           | 80   | creds d'un `ObjectBucketClaim`       |
| Gitea (forge GitOps) | `gitea-http.gitea.svc.cluster.local`         | 80   | Secret `gitea-admin` (mot de passe)  |
| Argo CD (GitOps)     | `argocd-server.argocd.svc.cluster.local`     | 80   | Secret `argocd-initial-admin-secret` |

Exposition **hors cluster** (UI) via le Gateway Cilium + TLS interne
([ADR 0020](decisions/0020-exposition-reseau-tout-cilium.md)/[0021](decisions/0021-cert-manager-ca-interne.md))
: p. ex. `https://dagster.cluster.lan`, `https://marquez.cluster.lan` (hostnames
`*.cluster.lan` = **placeholders génériques** ; l'admin réseau pose les vrais).

> **Version machine-lisible.** Cette table (et les StorageClasses / namespaces /
> conventions de secrets) est aussi publiée comme **contrat versionné** sous
> [`contract/`](../contract/) — diff-able et consommable par un script
> ([ADR 0043](decisions/0043-contrat-interface-cluster-atlas.md)). Ce guide en
> est la version pédagogique ; `contract/`, la version donnée.

## PostgreSQL (CloudNativePG)

Un cluster HA unique `pg` (namespace `postgres`) porte **trois bases logiques**,
chacune avec son rôle propriétaire
([ADR 0024](decisions/0024-postgres-manage-cloudnative-pg.md)) :

| Base       | Rôle (login) | Usage                                         |
| ---------- | ------------ | --------------------------------------------- |
| `dagster`  | `dagster`    | event log de l'orchestrateur                  |
| `pgvector` | `pgvector`   | recherche sémantique (extension SQL `vector`) |
| `marquez`  | `marquez`    | store de lineage (migrations Flyway)          |

**Connexion** : écrire (`pg-rw`) ou lire (`pg-ro`). Le mot de passe d'un rôle
est dans le Secret `pg-role-<rôle>` (clé `password`), namespace `postgres` —
n'employez **jamais** le mot de passe en clair, lisez-le du Secret :

```bash
# Exemple générique : récupérer le mot de passe du rôle dagster.
kubectl -n postgres get secret pg-role-dagster -o jsonpath='{.data.password}' | base64 -d
```

```python
# Exemple générique (psycopg) — depuis un pod, le pwd vient d'une var d'env
# injectée par un secretKeyRef (jamais en dur).
import os, psycopg
conn = psycopg.connect(
    host="pg-rw.postgres.svc.cluster.local", port=5432,
    dbname="pgvector", user="pgvector", password=os.environ["PG_PASSWORD"],
)
```

> **pgvector** : l'extension SQL s'appelle `vector` (pas `pgvector`). Le
> `CREATE EXTENSION vector` est déjà fait par l'operator ; utilisez le type
> `vector(n)` dans vos tables.

**Prérequis réseau** : votre pod doit avoir une NetworkPolicy egress vers
`postgres:5432` (cf.
`platform/network-policies/<app>/allow-postgres-egress.yaml` comme modèle).

## Lineage — OpenLineage → Marquez

Émettez des événements **OpenLineage** vers l'API Marquez ; ils y sont ingérés
et visualisés ([ADR 0028](decisions/0028-orchestration-openlineage-marquez.md)).
Le client OpenLineage standard lit ces variables d'environnement :

| Variable                | Valeur (intra-cluster)                           |
| ----------------------- | ------------------------------------------------ |
| `OPENLINEAGE_URL`       | `http://marquez.marquez.svc.cluster.local:5000`  |
| `OPENLINEAGE_ENDPOINT`  | `api/v1/lineage`                                 |
| `OPENLINEAGE_NAMESPACE` | le namespace logique de vos jobs (ex. `dagster`) |

**Requêter** le lineage (lecture) via l'API REST Marquez, p. ex. lister les jobs
d'un namespace :

```bash
# Depuis un pod du cluster :
wget -qO- http://marquez.marquez.svc.cluster.local:5000/api/v1/namespaces/<ns>/jobs
```

> **Réseau** : Marquez n'accepte le POST de lineage que depuis un namespace
> autorisé (cf. `allow-openlineage-ingress.yaml`) ; votre pod émetteur a besoin
> de l'egress correspondant (`allow-marquez-egress.yaml` côté Dagster en est le
> modèle — leçon du drift L19).

## Orchestration — Dagster

L'orchestrateur Dagster est livré **vide** (aucune code-location) : c'est le
**socle**, votre code (assets, jobs) s'y branche depuis `atlas`
([ADR 0026](decisions/0026-orchestration-dagster.md), frontière ADR 0022).

- **Storage** : Dagster persiste son event log dans la base CNPG `dagster` (déjà
  câblé via le Secret dérivé `dagster-pg-auth`).
- **Exécution** : `K8sRunLauncher` — chaque run devient un Job Kubernetes.
- **UI** : `https://dagster.cluster.lan` (Gateway, placeholder).
- **Brancher du code** : ajoutez une _code-location_ (workspace) pointant votre
  image — voir la doc `atlas`. Émettez le lineage via le sensor OpenLineage en
  pointant les variables ci-dessus.

## Déployer depuis atlas — la boucle GitOps

Vous ne déployez **pas** vos workflows avec `kubectl`. Le mécanisme
([ADR 0044](decisions/0044-topologie-deploiement-banc-atlas.md)/[0045](decisions/0045-chemins-installation-banc-couches.md))
est **pull-GitOps** :

1. **Build + push** votre image (code-location/job) dans le **registry interne**
   (`registry:80/...`, cf. section ci-dessous).
2. **Commit + push** le manifeste qui la référence (`Application` Argo CD, ou
   patch de workspace) dans le **dépôt Gitea intra-cluster** (la forge du banc ;
   pas un GitHub externe — le cluster est isolé, ADR 0003).
3. Un **webhook** Gitea → Argo CD déclenche la **réconciliation** : Argo CD
   applique votre manifeste (`Synced/Healthy`).
4. Le run s'exécute (`K8sRunLauncher`) et **émet du lineage** ingéré par
   Marquez.

> **Frontière (ADR 0022/0045).** Argo CD déploie **vos workflows**
> (code-locations, assets, jobs), **jamais l'infra** : CNPG, Dagster, Marquez,
> Argo CD lui-même sont montés par le socle (Ansible). Vous poussez le
> _contenu_, le socle fournit le _contenant vide_. Référence machine-lisible :
> [`contract/`](../contract/).

**Observabilité de vos workloads** (le socle fournit les opérateurs ; vous les
consommez en émettant des objets) :

- **Métriques** : exposez un `ServiceMonitor`/`PodMonitor` → Prometheus scrape
  automatiquement (kube-prometheus-stack).
- **Logs** : écrivez sur stdout/stderr → Loki les collecte (DaemonSet), sans
  action de votre part.
- **TLS d'une UI** : annotez votre `Gateway`
  `cert-manager.io/cluster-issuer: internal-ca` → certificat émis
  automatiquement (cf. « Exposition réseau » plus bas).

## Images — registry interne

Vos images applicatives (code-location Dagster, jobs) se poussent dans le
**registry interne** ([ADR 0011](decisions/0011-registry-http-sans-auth.md)) :

- Référencez-les en `registry:80/<repo>:<tag>` dans vos manifestes/CR.
- Les nœuds tirent ce registry en HTTP (config containerd posée par la
  plateforme : `use_local_image_pull`, certs.d — drifts L9/L13).
- **arm64** : sur le banc, les images maison sont buildées en interne ; en prod
  x86, les images officielles sont re-taguées (cf.
  [ADR 0006](decisions/0006-matrice-de-versions-et-politique-de-bump.md)).

## Stockage

### Bloc (PVC) — bases, état applicatif

StorageClasses disponibles (défaut = `rook-ceph-block-replicated`, RBD ×3,
[ADR 0001](decisions/0001-replication-x3-pour-workloads-bloc.md)) :

| StorageClass                 | Profil                                 |
| ---------------------------- | -------------------------------------- |
| `rook-ceph-block-replicated` | RBD ×3 — **défaut**, stateful critique |
| `rook-ceph-block-ec`         | erasure coded — gros volumes tolérants |
| `rook-cephfs`                | RWX (partagé multi-pods)               |

```yaml
# PVC générique :
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: rook-ceph-block-replicated
  resources: { requests: { storage: 10Gi } }
```

### Objet (S3) — datalake, artefacts

Demandez un bucket via un **ObjectBucketClaim** (Rook provisionne le bucket + un
Secret de creds dans votre namespace) :

```yaml
apiVersion: objectbucket.io/v1alpha1
kind: ObjectBucketClaim
metadata: { name: mon-bucket, namespace: <votre-ns> }
spec:
  generateBucketName: mon-bucket
  storageClassName: rook-ceph-datalake
```

Le Secret généré (même nom que l'OBC) porte `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` ; l'endpoint S3 est
`http://rook-ceph-rgw-datalake.rook-ceph:80` (path-style, HTTP intra-cluster).
Détail :
[`storage/ceph/storageClass/datalake/`](../storage/ceph/storageClass/datalake/).

## Exposition réseau (UI hors cluster)

Pour exposer une UI, ajoutez un `HTTPRoute` rattaché au Gateway Cilium, avec TLS
émis par la CA interne (annotation
`cert-manager.io/cluster-issuer: internal-ca`) — patron :
[`platform/dagster/gateway.yaml`](../platform/dagster/gateway.yaml). Le hostname
`*.cluster.lan` est un **placeholder** ; l'admin réseau pose le vrai.

## Travailler en local sur le banc multi-node-3 (chemin atlas)

En développement, vous ne consommez pas un cluster de production : vous montez
un **banc local** et vous y rejouez la boucle GitOps complète. Cette section
décrit la convention de bout en bout.

### Monter le banc

La topologie locale de référence est **`multi-node-3`** (1 control plane + 2
workers, banc Lima — ADR
[0030](decisions/0030-nomenclature-bancs-topologies.md)/[0040](decisions/0040-terrains-x-topologies.md)).
Le **chemin nommé** `atlas` enchaîne tout le socle DataOps + GitOps sur un
profil léger `local-path` (pas de Ceph — ADR
[0044](decisions/0044-topologie-deploiement-banc-atlas.md)/[0045](decisions/0045-chemins-installation-banc-couches.md))
:

```bash
# socle léger → monitoring → gitops (Gitea + Argo CD) → dataops → gitops-seed
test/lima/run-phases.sh atlas
# (variante stockage réel : test/lima/run-phases.sh atlas-ceph)
```

La dernière phase, **`gitops-seed`**
([`test/lima/gitea-init.sh`](../test/lima/gitea-init.sh)), initialise le dépôt
Gitea du banc : elle crée l'organisation `atlas` + le dépôt `workflows`, y
pousse un **workflow jouet**, pose le **webhook** Gitea → Argo CD et
l'`Application` `atlas-workflows`. À partir de là, tout `push` sur ce dépôt
déclenche une réconciliation. État du banc et UIs disponibles :

```bash
test/lima/run-phases.sh status   # VMs, nœuds, phases franchies, UIs, dernier run
```

> **`kubectl top` (usage CPU/mémoire).** Le chemin `atlas` ne déploie **pas**
> metrics-server (palier 1, ADR [0016](decisions/0016-observabilite.md)) :
> `kubectl top nodes` renvoie alors « Metrics API not available ». Pour
> l'activer : `kubectl apply -f platform/metrics-server/metrics-server.yaml`,
> puis `kubectl top nodes` / `kubectl top pods -A`. (Prometheus, lui, est déjà
> là et collecte ces mêmes métriques par une autre voie.)

Ces noms (`atlas`, `workflows`, `atlas-admin`) sont des **exemples génériques**
surchargeables par l'environnement (`GITEA_ORG`, `GITEA_REPO`,
`GITEA_ADMIN_USER`… — ADR
[0023](decisions/0023-plateforme-exemple-generique.md)). Adaptez aux valeurs de
votre déploiement.

### Atteindre les UIs et services depuis votre poste

Les hostnames `*.cluster.lan` (`https://dagster.cluster.lan`,
`argocd.cluster.lan`…) sont des **placeholders** : ils ne résolvent pas en
local, et l'IP du Gateway (`LB-IPAM`, réseau interne de la VM) n'est pas
routable depuis l'hôte. La voie fiable en local est **`kubectl port-forward`**,
avec le kubeconfig du banc :

```bash
export KUBECONFIG=test/lima/.work/kubeconfig

# Argo CD : http://127.0.0.1:8080  (server.insecure ⇒ HTTP en clair, pas https)
kubectl -n argocd port-forward svc/argocd-server 8080:80
# Gitea   : http://127.0.0.1:3000
kubectl -n gitea  port-forward svc/gitea-http   3000:80
# Dagster : http://127.0.0.1:3001
kubectl -n dagster port-forward svc/dagster-dagster-webserver 3001:80
# Marquez : http://127.0.0.1:3002
kubectl -n marquez port-forward svc/marquez-web 3002:3000
# Grafana : http://127.0.0.1:3003  (identifiants : admin / cf. secret ci-dessous)
kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3003:80
```

> **Nom du service Grafana.** Il s'appelle `kube-prometheus-stack-grafana`
> (préfixe du chart), pas `grafana`. Mot de passe admin :
> `kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d`.

Mots de passe d'admin (lus depuis les Secrets, jamais en clair dans le dépôt) :

```bash
# Argo CD (utilisateur admin)
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
# Gitea (utilisateur atlas-admin, créé par gitops-seed)
kubectl -n gitea get secret gitea-admin \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

### Pousser sur Gitea

C'est l'acte central de la boucle : **vous poussez vos manifestes dans le dépôt
Gitea du banc**, Argo CD les réconcilie (vous ne faites **jamais** de
`kubectl apply` de vos workflows — frontière ADR
[0022](decisions/0022-argocd-gitops-applicatif.md)). Comme Gitea n'est joignable
qu'en intra-cluster, on passe par un **port-forward** :

```bash
# 1) Forward du HTTP Gitea (laisser tourner dans un terminal) :
export KUBECONFIG=test/lima/.work/kubeconfig
kubectl -n gitea port-forward svc/gitea-http 3000:80

# 2) Récupérer les identifiants atlas-admin :
GITEA_USER=$(kubectl -n gitea get secret gitea-admin -o jsonpath='{.data.username}' | base64 -d)
GITEA_PW=$(kubectl -n gitea get secret gitea-admin   -o jsonpath='{.data.password}' | base64 -d)

# 3) Cloner le dépôt seedé (org/dépôt = exemples génériques atlas/workflows) :
git clone "http://${GITEA_USER}:${GITEA_PW}@127.0.0.1:3000/atlas/workflows.git"
cd workflows

# 4) Modifier/ajouter un manifeste (Application, patch de workspace…), committer,
#    puis pousser sur main → le webhook déclenche Argo CD :
git add . && git commit -m "feat: nouveau workflow"
git push origin main
```

> **Authentification.** Mettre le mot de passe dans l'URL est commode pour un
> banc jetable ; préférez un **token d'accès personnel** (UI Gitea → _Settings →
> Applications_) ou un credential helper pour un usage répété. Le webhook `push`
> → Argo CD est déjà posé par `gitops-seed` : un `push` réussi entraîne la
> réconciliation (visible dans l'UI Argo CD, `Synced/Healthy`). À défaut de
> webhook, Argo CD repolle de toute façon périodiquement.

Vérifier le résultat : l'`Application` passe `Synced/Healthy` (UI Argo CD), le
run s'exécute (`K8sRunLauncher` → Job K8s) et **émet du lineage** ingéré par
Marquez.

## Pour aller plus loin

- Présentation des briques : [composants](composants.md).
- Architecture transverse : [vues d'architecture](architecture/).
- Décisions : [index ADR](decisions/). Chaque brique a son README dans
  `platform/<brique>/` et `storage/ceph/`.
- Mettre la plateforme en place :
  [`bootstrap/dataops.yaml`](../bootstrap/dataops.yaml) (ADR
  [0033](decisions/0033-orchestration-ansible-platform-dataops.md)).
