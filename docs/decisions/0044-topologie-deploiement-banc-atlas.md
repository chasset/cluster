# 0044 — Topologie de déploiement du banc atlas (socle consommé, Gitea intra-banc)

## Contexte

Le travail se répartit sur **deux dépôts** : `cluster` (ce dépôt — le **socle
d'infrastructure** générique) et `atlas` (le dépôt **applicatif/métier**). La
frontière est posée par [ADR 0023](0023-plateforme-exemple-generique.md) (le
métier vit dans `atlas`), [ADR 0022](0022-argocd-gitops-applicatif.md) (Argo CD
déploie l'applicatif via l'`AppProject` `atlas`) et formalisée comme interface
machine-lisible par [ADR 0043](0043-contrat-interface-cluster-atlas.md).

Ces ADR décrivent le **runtime** (où `atlas` se branche : endpoints,
StorageClasses, secrets) mais **pas le mécanisme de déploiement** : qui monte le
cluster sur lequel `atlas` tourne, et par quel canal le code `atlas` arrive dans
ce cluster. Deux questions restaient implicites :

- **Q1 — montage du socle.** `atlas` doit pouvoir **valider son code sur un banc
  reproductible** : un cluster Kubernetes avec le socle DataOps (Cilium,
  cert-manager, Rook/Ceph, CNPG, Argo CD, Dagster, Marquez). Or ce socle, et le
  harnais qui le monte, **vivent dans `cluster`**. Comment `atlas` les
  consomme-t-il sans les redévelopper ni les copier (drift garanti, contraire à
  ADR 0023) ?
- **Q2 — entrée GitOps.**
  L'[`AppProject` `atlas`](../../platform/argocd/appproject-atlas.yaml)
  n'autorise aujourd'hui qu'un `sourceRepos : cluster.git`. Mais les
  `Application` qu'Argo CD réconcilie (code-locations Dagster, apps
  `citation-*`) référencent du **code qui vit dans `atlas`**. Le `sourceRepos`
  actuel est donc soit incomplet, soit faux — et **graver `atlas.git` en dur**
  dans le manifeste générique violerait ADR 0023 (valeur propre à un
  déploiement).

Fait cadrant : le banc Lima de `cluster` monte déjà la **seule topologie locale,
`multi-node-3`** (1 control-plane + 2 workers, quorum mon Ceph + réplication ×3,
[ADR 0040](0040-terrains-x-topologies.md)), via
[`bench/lima/run-phases.sh`](../../bench/lima/run-phases.sh) — phases
idempotentes, gates, paramétré par inventaire/`group_vars` **non versionnés**
surchargeant des `.example`. Le banc est prouvable **from-scratch**
([ADR 0034](0034-validation-e2e-from-scratch.md)). `atlas` n'a donc **pas à
inventer** un banc : il réutilise celui-ci.

## Décision

**Le banc `atlas` est le banc `multi-node-3` du socle `cluster`, consommé comme
une release versionnée et paramétré par la config locale d'`atlas`. L'entrée
GitOps (`sourceRepos`) devient une valeur surchargeable, défaut générique.**

1. **Q1 — `cluster` est consommé comme release, harnais de banc inclus.** Une
   release `cluster` (tag, matrice de versions
   [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) expose le
   **harnais de banc complet** : `bootstrap/` (playbooks Ansible), `platform/`
   (manifestes figés), `bench/lima/` (montage `multi-node-3`) et
   [`contract/`](../../contract/) (interface). `atlas` **pinne une version** du
   socle et monte son banc avec ses propres `group_vars`/inventaire (non
   versionnés, patron `.example`). Ni sous-module, ni copie : une dépendance
   versionnée, alignée sur la politique de bump existante.

2. **Q2 — `sourceRepos` est un placeholder surchargeable.** Le `sourceRepos` de
   l'`AppProject` `atlas` porte un **défaut générique** (`cluster.git`, valeur
   d'exemple) **surchargé** par le déploiement `atlas` vers son dépôt réel, via
   le patron ADR 0023 (`lookup('env','X') | default('<exemple>')` ou surcharge
   d'inventaire). **Aucune** valeur propre à un déploiement (`atlas.git` réel)
   n'est gravée dans le manifeste versionné de `cluster`.

3. **Source git : Gitea hébergé DANS le banc (air-gapped).** Argo CD pull les
   manifestes depuis un **dépôt git hébergé dans le banc par Gitea** (et non
   depuis un remote GitHub public). Ce choix reproduit la contrainte **prod** —
   cluster **isolé, sans Internet**
   ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md),
   [ADR 0022](0022-argocd-gitops-applicatif.md), images Argo CD déjà mirrorées
   dans le registry interne pour la même raison) — donc le banc **prouve** le
   flux GitOps tel qu'il tournera en prod, sans dépendre d'un egress vers
   `github.com`. Le `sourceRepos` surchargé (point 2) pointe alors une URL
   **intra-banc** servie par Gitea (p. ex.
   `http://gitea-http.gitea.svc/<org>/atlas.git`), pas `github.com`.

   **Initialisation post-bootstrap** : Gitea est posé par le socle (Ansible,
   infra — il fait partie de ce qui doit converger _avant_ qu'Argo CD
   réconcilie). Une fois le bootstrap terminé, une **phase d'initialisation du
   dépôt** (idempotente, dans le harnais `bench/lima/`) crée l'organisation et
   le dépôt dans Gitea, puis **seed/push** le contenu `atlas` (manifestes
   `Application`, code-locations) — c'est ce que l'`AppProject` réconciliera
   ensuite. Ordre :
   `bootstrap (infra + Gitea) → init dépôt Gitea (seed atlas) → Argo CD sync`.
   Le smoke-test guestbook actuel (repoURL GitHub public) reste un smoke-test
   **zéro-dépendance** distinct, hors de ce modèle air-gapped.

4. **Webhook Gitea → Argo CD (déploiement réactif, pas de polling).** Gitea est
   configuré (à l'init du dépôt) avec un **webhook** vers `…/api/webhook`
   d'`argocd-server` : un push déclenche **immédiatement** la réconciliation au
   lieu d'attendre le polling par défaut (~3 min, `timeout.reconciliation`). Le
   webhook est **authentifié par un secret partagé** (clé `webhook.gitea.secret`
   de `argocd-secret`, même valeur posée côté Gitea), généré à l'init (jamais
   versionné — patron ADR 0023). Réseau : l'appel est **intra-cluster** Gitea →
   `argocd-server:8080` ; l'ingress est déjà ouvert
   ([`allow-server-ingress.yaml`](../../platform/network-policies/argocd/allow-server-ingress.yaml),
   source non restreinte côté bordure Cilium) et l'egress repo-server → Gitea
   l'est aussi
   ([`allow-egress.yaml`](../../platform/network-policies/argocd/allow-egress.yaml),
   ports git 80/443/22/9418). Aucune nouvelle NetworkPolicy requise ; reste à
   **poser le secret** et **enregistrer le webhook côté Gitea**. Le port
   `webhook` du Service `argocd-server` existe déjà dans le bundle épinglé.

5. **`multi-node-3`, stockage `local-path`.** Le banc `atlas` réutilise le
   harnais existant (`bench/lima/run-phases.sh`) tel quel — mêmes phases, mêmes
   gates, même topologie ([ADR 0040](0040-terrains-x-topologies.md)) — en
   **profil `local-path`** (phase `storage-simple`, défaut du harnais ; **pas**
   `WITH_CEPH=1`). Justifié : `atlas` itère sur l'**applicatif/métier**, pas sur
   la couche stockage ; `local-path` monte en ~30 s contre ~15 min pour Ceph
   ([ADR 0035](0035-strategie-bancs-fidelite-vitesse.md)). Conséquence
   d'interface : sur ce profil la SC `default` est `local-path` (RWO mono-nœud,
   pas de RWX ni d'erasure-coding) et **il n'y a pas de RGW Ceph** — le backing
   S3 (datalake, backups Barman) passe par l'alternative banc-léger
   ([ADR 0036](0036-backing-s3-unique-rgw.md), SeaweedFS) ou est hors périmètre
   du banc `atlas`. La seule autre variation est la **config locale** d'`atlas`
   (inventaire, `group_vars`, `sourceRepos`, hostnames). Le harnais ne se
   duplique pas.

6. **Frontière préservée (anti-bootstrap-circulaire, ADR 0022).** Le banc
   `atlas` converge **d'abord par Ansible** (infra : kubeadm, Cilium,
   cert-manager, Rook, CNPG, **Argo CD lui-même**), **puis** l'Argo CD ainsi
   posé réconcilie l'applicatif `atlas` depuis le `sourceRepos` surchargé.
   cert-manager, Prometheus, Loki restent des **opérateurs passifs** posés par
   le socle : `atlas` les consomme en émettant des CR/annotations
   (`ServiceMonitor`, TLS), il ne les « lance » pas.

7. **Test d'intégration end-to-end (gate de preuve).** La chaîne décidée ici est
   validée par une **phase d'intégration** du harnais `bench/lima/`, qui prouve
   le flux **complet** dans l'ordre — chaque étape est un **gate** (exit ≠ 0 si
   le critère n'est pas atteint), idempotent et rejouable comme les phases
   existantes ([ADR 0034](0034-validation-e2e-from-scratch.md)) :
   1. **Créer le dépôt** dans Gitea (org + repo) et **poser le webhook** + le
      secret partagé — gate : le dépôt répond, le webhook est enregistré.
   2. **Push** un commit applicatif (manifeste `Application` + une code-location
      `atlas` d'exemple générique) — gate : la ref est présente côté Gitea.
   3. **Argo CD déploie** : la réconciliation déclenchée par le webhook amène
      l'`Application` à **`Synced/Healthy`** — gate : statut atteint sous un
      délai (preuve que le webhook, pas le polling, a déclenché).
   4. **DataOps tourne** : la code-location déployée exécute un run Dagster qui
      **réussit** et **émet du lineage** ingéré par Marquez — gate : réutilise
      la logique d'assertion existante
      ([`dataops-assert.sh`](../../bench/lima/dataops-assert.sh) :
      `classify_dagster_run`, `classify_marquez_ingest`).

   La logique de décision est **isolée et testée** (prédicats purs, couverts
   hors cluster), le **choix de langage** suivant la frontière de
   [ADR 0017](0017-langage-des-scripts.md) (orchestration de CLIs → bash ;
   logique complexe → Python ; fonctions bash pures → bats) — non figé ici. Le
   run est consigné comme **preuve de banc**
   ([ADR 0042](0042-fraicheur-preuves-banc.md), surveillé par le garde-fou de
   fraîcheur).

## Statut

Accepted (2026-06-09).

## Conséquences

- **Gain** : `atlas` obtient un banc reproductible **sans redévelopper le
  socle** ni le copier — une release pinnée, surchargée localement. Le sens du
  flux de déploiement (commit `atlas` → Argo CD du banc réconcilie) devient
  explicite et documentable (mise à jour à venir de
  [`docs/guide-dev-data.md`](../guide-dev-data.md), section « déployer depuis
  atlas »).
- **`sourceRepos` corrigé sans violer ADR 0023** : la valeur générique reste
  versionnée, la valeur réelle (`atlas.git`) vit en config locale. Lève
  l'ambiguïté de l'`AppProject` sans graver une spécificité de déploiement.
- **Prix à payer** : `cluster` doit **garantir** que le harnais de banc
  (`bootstrap/` + `platform/` + `bench/lima/`) reste consommable par un tiers —
  c'est-à-dire que **toute** spécificité de déploiement passe bien par les
  `.example` surchargeables, jamais par un défaut versionné. Cette discipline,
  déjà imposée par ADR 0023, devient un **contrat envers `atlas`**.
- **Couplage de version** : `atlas` pinne une version du socle ; un bump
  `cluster` (Kubernetes, CRDs, endpoints) peut exiger une mise à jour côté
  `atlas`. Tracé par la matrice de versions
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) et le contrat
  diff-able ([ADR 0043](0043-contrat-interface-cluster-atlas.md)).
- **Hors périmètre** : le mécanisme exact de packaging d'une release (archive de
  tag, artefact dédié, rôle Ansible publié) n'est pas tranché ici — l'option «
  artefact/role séparé partagé par `cluster` et `atlas` » reste une évolution
  possible, prématurée tant que `cluster` est l'unique producteur du harnais.
- **Coût de Gitea intra-banc (air-gapped)** : reproduire la contrainte prod «
  sans Internet » impose d'**héberger Gitea** dans le banc (pod + PVC
  `local-path`) et d'**initialiser le dépôt** post-bootstrap (créer org/dépôt,
  seed/push du contenu `atlas`) — une brique + une phase de plus dans le
  harnais, à outiller et à garder idempotentes. Bénéfice : le banc **prouve** le
  flux GitOps tel qu'il tournera en prod isolée
  ([ADR 0003](0003-pas-de-chiffrement-ceph-tailscale.md)), sans masquer la
  dépendance derrière un egress GitHub qui n'existera pas en prod.
- **Frontière infra/app pour Gitea (ADR 0022)** : Gitea est de l'**infra** (il
  doit converger avant qu'Argo CD réconcilie → Ansible, pas une `Application`,
  sous peine de bootstrap circulaire). L'**init du dépôt** (seed atlas) est en
  revanche une étape de **données**, post-bootstrap, hors du périmètre Argo CD.
- **Réactivité** : le webhook Gitea → Argo CD ramène la latence de déploiement
  de l'ordre de la **minute** (polling) à la **seconde** (push) — important pour
  une boucle d'itération `atlas` sur un banc. Le polling reste le **filet de
  sécurité** si un webhook est manqué (Argo CD garde son
  `timeout.reconciliation`).
- **À faire (suite)** : (a) rendre `sourceRepos` surchargeable dans
  [`appproject-atlas.yaml`](../../platform/argocd/appproject-atlas.yaml), défaut
  générique intra-banc ; (b) outiller **Gitea (infra) + la phase d'init du
  dépôt** (seed atlas) dans le harnais `bench/lima/` ; (c) **enregistrer le
  webhook Gitea → Argo CD + poser le secret partagé** (`webhook.gitea.secret`) à
  l'init ; (d) documenter le flux « déployer depuis atlas » + l'observabilité
  (`ServiceMonitor` Prometheus, collecte Loki, annotation cert-manager) dans le
  guide dev-data ; (e) ajouter Argo CD (et Gitea) au contrat
  ([`contract/endpoints.example.yaml`](../../contract/endpoints.example.yaml)) ;
  (f) **phase de test d'intégration end-to-end** (créer dépôt Gitea → push →
  Argo CD `Synced/Healthy` → run Dagster + lineage Marquez), logique d'assertion
  isolée et testée (langage selon ADR 0017), run consigné comme preuve de banc
  (ADR 0042).
