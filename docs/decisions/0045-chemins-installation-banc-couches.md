# 0045 — Chemins d'installation du banc : couches, dépendances, tests associés

## Contexte

Le harnais de banc [`test/lima/run-phases.sh`](../../test/lima/run-phases.sh)
expose une douzaine de phases (`up`, `bootstrap`, `storage-simple`, `ceph`,
`sc`, `datalake`, `dataops`, `gitops`, `monitoring`…) et un agrégat `all`. Au
fil des ajouts (DataOps #173, métrologie #219, socle GitOps #230), `all` a pris
un rôle **ambigu** : il sert à la fois de **smoke-test rapide du socle**
(`up → bootstrap → storage-simple`) et de point d'entrée vers un **banc
utilisable**, sans que les **chemins** ni l'**ordre des couches** soient
explicitement décidés.

Trois constats motivent une clarification :

1. **L'ordre entre briques applicatives n'est pas trivial.** `monitoring`,
   `gitops`, `dataops` sont **sœurs** (aucune ne dépend d'une autre) — l'ordre
   entre elles est un **choix**, pas une contrainte. Or l'observabilité
   (Prometheus/Loki) ne capte le démarrage des autres briques que si elle est
   **en place avant elles**.
2. **`monitoring` est autonome mais piégeux.** Il déploie lui-même son backing
   S3 (SeaweedFS en mode léger, `when: loki_s3_backing == seaweedfs`) ; sa seule
   dépendance est un cluster Ready + une StorageClass. Mais lancé sans propager
   le profil, il choisit le mauvais backing (drift L44).
3. **Le branchement de stockage est le vrai point de divergence** (mode léger
   `local-path` / mode Ceph), et tout l'applicatif en dépend (StorageClass +
   backing S3).

Sans décision, l'ordre des phases est gravé au coup par coup dans un script, et
`all` veut dire deux choses à la fois.

## Décision

**Modèle en couches explicite, observabilité posée tôt, et chemins
d'installation nommés.**

### 1. Couches et dépendances (l'ordre vient des dépendances, pas de l'habitude)

```text
socle           : up → bootstrap → platform-prereqs
  └─ stockage    : [léger] storage-simple        | [ceph] ceph → sc → datalake
       └─ applicatif (briques SŒURS, dépendent du stockage, pas l'une de l'autre) :
            monitoring   (cluster + SC ; déploie son backing S3)
            gitops       (cluster + SC ; PVC Gitea)
            dataops      (cluster + SC + backing S3 Barman)
```

`monitoring`, `gitops`, `dataops` ne dépendent que de la **couche stockage** (un
cluster Ready + une StorageClass `default` + un backing S3 pour celles qui font
du S3) — **jamais l'une de l'autre**. L'ordre entre elles est donc libre, et se
décide par un critère : **l'observabilité d'abord**.

### 2. Observabilité précoce

`monitoring` est posé **juste après la couche stockage**, **avant** `gitops` et
`dataops` : Prometheus/Loki captent alors les métriques et logs du démarrage des
autres briques (et du futur applicatif `atlas` réconcilié par Argo CD) dès le
premier instant, pas après coup.

### 3. Chemins d'installation nommés (lève l'ambiguïté de `all`)

- **`socle`** — `up → bootstrap → storage-simple` : smoke-test rapide du socle
  (le rôle « rapide » historique de `all`, inchangé).
- **`atlas`** (mode léger, ADR 0044) — `socle → monitoring → gitops`. Banc atlas
  utilisable ; `dataops` n'y figure **pas** : sur le banc atlas, la chaîne
  DataOps est réconciliée **par Argo CD depuis Gitea** (GitOps, #231), pas par
  Ansible (frontière ADR 0022).
- **`cluster`** (mode Ceph, preuve stockage réel) —
  `up → bootstrap → ceph → sc → datalake → monitoring → dataops` : la chaîne
  DataOps par Ansible reste légitime ici (pas d'Argo CD dans ce chemin).

`all` est conservé pour compatibilité mais documenté comme **alias du chemin
selon `WITH_CEPH`** ; les noms ci-dessus sont la référence.

### 4. Chaque couche porte ses tests (gate + assertion)

Un chemin n'est pas qu'une séquence de phases : **chaque couche déclare ce qui
prouve qu'elle a réussi**. Deux niveaux, déjà présents dans le harnais :

- **Gate de phase** (dans `run-phases.sh`) : vérification bloquante en fin de
  phase (exit ≠ 0 sinon), sur cluster réel.
- **Assertion pure** (logique de décision isolée, testée hors cluster en
  `test/unit/*.bats` — ADR 0017) : classe un état observé en ok/ko, réutilisée
  par le gate.

| Couche / phase   | Gate de phase (preuve sur banc)                                                                      | Assertion (test unitaire) |
| ---------------- | ---------------------------------------------------------------------------------------------------- | ------------------------- |
| `up`             | disques attendus présents (`vdb..vde` si Ceph)                                                       | —                         |
| `bootstrap`      | N nœuds **Ready** (Cilium up)                                                                        | `state-classify.bats`     |
| `storage-simple` | provisioner Ready + **PVC `local-path` Bound** (`gate_test_pvc`)                                     | —                         |
| `ceph`           | operator Ready + **`HEALTH_OK`**                                                                     | —                         |
| `sc`             | **PVC Bound** sur la SC Ceph par défaut                                                              | —                         |
| `datalake`       | **RGW Ready** (cible S3 Barman)                                                                      | —                         |
| `monitoring`     | Prometheus + Grafana + Loki (S3/backing) **Ready**                                                   | `metrology.bats`          |
| `gitops`         | `deploy/gitea` + `deploy/argocd-server` **Ready** (rollout)                                          | — (e2e à venir #231)      |
| `dataops`        | CNPG sain, Dagster/Marquez Ready, **lineage d'un run réel ingéré** (`dataops_chain_emit_and_verify`) | `dataops-assert.bats`     |

Règle : **toute nouvelle couche ajoute son gate** (et une assertion pure si la
décision est non triviale) ; un chemin n'est « validé » que si **tous les gates
de ses couches passent**, et le run est **consigné** (ADR 0034/0042). Les
chemins diffèrent donc aussi par leur **batterie de preuves** :

- `socle` : gates `up` → `bootstrap` → `storage-simple`.
- `atlas` : ceux de `socle` + `monitoring` + `gitops` (+ e2e GitOps→DataOps
  #231).
- `cluster` : `up` → `bootstrap` → `ceph` → `sc` → `datalake` → `monitoring` →
  `dataops` (jusqu'au lineage réel).

### 5. Le profil de stockage se propage

Toute phase applicative reçoit explicitement StorageClass + backing S3 du profil
courant (déjà fait dans le harnais via `-e …`). Le drift L44 (monitoring sans
profil) est un invariant à ne pas régresser.

## Statut

Proposed.

## Conséquences

- **Ordre justifié, pas coutumier** : l'observabilité précède ce qu'elle observe
  ; les briques sœurs sont reconnues comme telles (réordonnables sans casse).
- **`all` désambiguïsé** : « smoke rapide » (`socle`) vs « banc utilisable »
  (`atlas`/`cluster`) ne sont plus confondus.
- **Frontière ADR 0022/0044 préservée** : `dataops` par Ansible **uniquement**
  dans le chemin `cluster` ; sur `atlas`, la chaîne vient de GitOps (#231) — pas
  de double déploiement.
- **Prix à payer** : le chemin `atlas` est plus lourd que l'ancien `all` rapide
  (monitoring = Prometheus + Loki + SeaweedFS, quelques minutes). D'où la
  distinction `socle` (rapide) vs `atlas` (complet), pour ne pas alourdir le
  smoke.
- **À faire (suite)** : implémenter les cibles nommées dans
  [`test/lima/run-phases.sh`](../../test/lima/run-phases.sh) (insérer
  `monitoring` avant `gitops` dans le chemin léger ; cibles `socle`/`atlas`/
  `cluster`), mettre à jour la doc du harnais, et consigner un run de chaque
  chemin (ADR 0034/0042). Hors périmètre de #230 (qui livre la brique GitOps).
