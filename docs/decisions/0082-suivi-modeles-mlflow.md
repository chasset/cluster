# 0082 — Suivi de modèles via MLflow

## Contexte

Le socle DataOps a un orchestrateur ([ADR 0026](0026-orchestration-dagster.md),
Dagster) et un store de lineage
([ADR 0028](0028-orchestration-openlineage-marquez.md), Marquez), tous deux
backés par le PostgreSQL managé
([ADR 0024](0024-postgres-manage-cloudnative-pg.md)). Manque le **suivi
d'expériences et le registre de modèles** : où sont loggués les runs (params,
métriques), les artefacts (modèles, courbes), et où s'enregistrent les versions
de modèles promues. Le standard de fait est **MLflow** (tracking server + model
registry + artefact store). Le code ML vit côté `atlas` (Phase 2+) ; ici on
déploie le **serveur seul**, comme Dagster est livré vide (ADR 0026).

## Décision

**MLflow tracking server** sur Kubernetes (image maison `registry:80/mlflow` =
officielle + psycopg2, cf. § Image amendé), dans `platform/mlflow/`, appliqué
par le rôle Ansible `platform-mlflow` comme les autres addons plateforme
(manifeste figé appliqué via `kubernetes.core.k8s`, ADR
[0033](0033-orchestration-ansible-platform-dataops.md)/[0049](0049-doctrine-choix-outil-par-action.md)
— pas Argo CD pour l'infra, frontière anti-bootstrap-circulaire ADR 0022).

- **Addon socle (vs côté atlas)** : MLflow est un service partagé
  multi-consommateur (comme Dagster/Marquez), géré par Ansible. Le namespace
  `mlflow` reste **destinataire Argo CD** (AppProject `atlas`) pour le futur
  code atlas, mais le serveur lui-même est posé par le socle.

- **Backend store = base CNPG dédiée `mlflow`** : cohérent avec
  `dagster`/`pgvector`/`marquez`.
  `--backend-store-uri postgresql://mlflow:<pwd>@pg-rw.postgres.svc:5432/mlflow`.
  La base est ajoutée au **cluster CNPG HA unique `pg`** (un seul cluster
  PostgreSQL porte toutes les bases applicatives). Le mot de passe vient d'un
  **Secret dérivé** `mlflow-pg-auth` (clé `postgresql-password`, alignée sur
  Dagster), recopié du Secret CNPG `pg-role-mlflow` — config locale non
  versionnée ([ADR 0023](0023-plateforme-exemple-generique.md)).

- **Artefact store = S3** via le rôle factorisé `platform-s3-bucket`
  ([ADR 0036](0036-backing-s3-unique-rgw.md)) :
  `--default-artifact-root s3://<bucket>/`, `MLFLOW_S3_ENDPOINT_URL` pointant le
  **backing actif** (RGW Ceph en prod / SeaweedFS au banc léger). Même chemin de
  code, backing paramétré ; le bucket OBC auto-nommé est résolu au runtime par
  le rôle (l'env `--default-artifact-root` est injectée à l'apply, comme Loki
  templise son endpoint S3). MLflow embarque `boto3` (artefact store S3
  fonctionnel).

- **InitContainer wait-for-db** (image `postgres` épinglée par digest d'index
  multi-arch, ADR 0006, réutilise le digest Marquez) : MLflow crée son schéma au
  premier démarrage (`mlflow db upgrade` implicite) → attendre que CNPG réponde.

- **Exposition de l'UI** via le Gateway Cilium + TLS interne
  ([ADR 0020](0020-exposition-reseau-tout-cilium.md)/[0021](0021-cert-manager-ca-interne.md)),
  **sans auth** : réseau privé de confiance mono-admin
  ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)), comme
  Dagster/Marquez. L'API/UI partagent le port 5000 (MLflow est un seul serveur).
  Les émetteurs (code atlas) la joignent par le Service ClusterIP
  `mlflow.mlflow.svc:5000` (variable `MLFLOW_TRACKING_URI`, pendant de
  `OPENLINEAGE_URL` pour Marquez).

- **Serveur livré configuré mais VIDE** : aucune expérience pré-créée ; `atlas`
  logue ses runs et enregistre ses modèles (précédent « orchestrateur vide »
  Dagster, ADR 0026).

### Image : maison multi-arch (officielle + psycopg2) — AMENDÉ (2026-06-17)

> **Décision initiale (caduque)** : « image officielle multi-arch, pas de build
> maison ». L'index `ghcr.io/mlflow/mlflow` est bien multi-arch (amd64+arm64,
> `v3.4.0`) et embarque `boto3` (S3) — mais **PAS `psycopg2`** (driver
> PostgreSQL). Or le backend store est une base CNPG
> (`--backend-store-uri postgresql://`) : `mlflow server` crashe au démarrage en
> `ModuleNotFoundError: No module named 'psycopg2'` (CrashLoopBackOff vécu, logs
> du 2026-06-17).

On **dérive donc une image maison**
`FROM ghcr.io/mlflow/mlflow:v3.4.0@<digest> + pip install psycopg2-binary`
([`platform/mlflow/image/Dockerfile`](../../platform/mlflow/image/Dockerfile)),
publiée dans le registry interne (`registry:80/mlflow:v3.4.0`) comme
Marquez/Dagster. Deux différences avec eux :

- on **ajoute** un paquet à une image déjà multi-arch (≠ rebuild d'une
  amd64-only) : l'image dérivée reste **multi-arch** (`psycopg2-binary` a des
  wheels manylinux + aarch64) → **pas de Play de build arm64-spécifique** ;
- mais elle doit être **buildée sur les DEUX arches** (et non retaguée de
  l'officielle en x86, sinon l'image x86 n'aurait pas psycopg2) → un flag
  **`build_all_arch: true`** dans `platform-build-images` force le build en x86
  comme en arm64.

La layer autonome `bootstrap/mlflow.yaml` gagne donc un play `hosts: cloud`
(containerd registry + `platform-build-images` sur `mlflow_build_images`) AVANT
le play k8s qui applique le manifeste tirant `registry:80/mlflow`. Référence par
TAG (pas digest), comme dagster/marquez — image buildée localement, pas un
upstream mutable.

## Statut

Proposed (2026-06-17). **Validation banc différée** : le banc Ceph a été détruit
; la convergence réelle (`bootstrap/mlflow.yaml` — play build image maison puis
play k8s) sera prouvée au prochain montage Ceph multi-node — image
`registry:80/mlflow` buildée (les 2 arches), base `mlflow` créée, OBC RGW
produisant le bucket + creds, pod MLflow Ready (PLUS de CrashLoopBackOff
psycopg2), un run loggué depuis atlas persistant params/métriques en base et
artefacts en S3, UI répondant sur `mlflow.cluster.lan` — à consigner dans
l'historique des runs (honnêteté des preuves, ADR 0052).

## Conséquences

**Bénéfices.**

- Suivi d'expériences + registre de modèles (MLflow, standard de fait), API +
  UI.
- Store HA/sauvegardé (base CNPG `mlflow`) + artefacts S3, pas d'infrastructure
  stateful supplémentaire (réutilise le cluster `pg` et le RGW datalake).
- Socle DataOps complet : orchestration (Dagster) + lineage (Marquez) + suivi de
  modèles (MLflow), les trois backés CNPG, le même pattern d'addon.
- **Image maison MINIMALE** (officielle + psycopg2, cf. § Image amendé) : plus
  légère à maintenir que Marquez/Dagster (on ajoute un paquet, pas de rebuild
  d'arch) — mais un build interne est désormais requis (registry interne,
  `build_all_arch`).

**Coûts assumés.**

- **API/UI sans auth** : acceptable sur réseau privé mono-admin ; à durcir si le
  cluster s'ouvre (oauth2-proxy en bordure).
- Le `--default-artifact-root` dépend du bucket OBC auto-nommé → résolu au
  runtime par le rôle Ansible (env injectée), pas figé dans le manifeste.

## Alternatives écartées

- **MLflow côté atlas (pas addon socle)** : MLflow est partagé
  multi-consommateur comme Dagster/Marquez ; le poser côté atlas le couplerait à
  un seul dépôt et recréerait la circularité bootstrap (ADR 0022). Addon socle
  retenu.
- **Schéma dans une base partagée** (plutôt qu'une base dédiée) : MLflow gère
  son historique de migrations par base ; une base dédiée `mlflow` (comme
  Marquez) isole proprement. Base dédiée retenue.
- **Un cluster CNPG dédié à MLflow** : doublerait l'infrastructure stateful HA
  pour un store modeste. Un seul cluster `pg` partagé (une base par appli)
  suffit.
- **Artefact store sur PVC (filesystem)** plutôt que S3 : ne survivrait pas à un
  reschedule sans RWX, et heurterait le pattern S3 factorisé (ADR 0036). S3
  (OBC) retenu, cohérent avec les backings du socle.
- **Rester sur l'image officielle sans build** (décision initiale) : impossible
  — l'officielle n'a pas `psycopg2`, le serveur crashe sur backend PostgreSQL.
  Une image maison minimale (officielle + psycopg2, multi-arch) est requise (cf.
  § Image amendé).
- **`pip install psycopg2` au démarrage du conteneur** (au lieu d'une image
  maison) : tire PyPI au boot (incompatible air-gap/prod) et réinstalle à chaque
  restart. Rejeté au profit de l'image maison reproductible (registry interne).

## À revoir

- Auth en bordure de l'UI (oauth2-proxy) si ouverture du cluster.
- Brancher un ServiceMonitor MLflow sur le monitoring (métriques du serveur).
- Politique de rétention des runs/artefacts à ajuster selon le volume réel.
- Si MLflow cesse de publier des images multi-arch : basculer sur image maison
  (le pattern Marquez reste disponible).
