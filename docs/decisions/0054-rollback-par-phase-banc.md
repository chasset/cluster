# 0054 — Rollback par phase sur le banc (désinstallation ciblée, jetable)

## Contexte

Le banc se monte **phase par phase** par un chemin nommé codé
([ADR 0045](0045-chemins-installation-banc-couches.md)) :
`bench/lima/run-phases.sh ceph|sc|datalake|monitoring|dataops|gitops…`. Mais il
n'existe **aucun moyen symétrique de DÉFAIRE une seule phase**. Pour re-tester
une phase proprement (itération de développement/validation), on n'a que deux
leviers, tous deux **globaux** :

- `run-phases.sh down` — détruit les **VMs Lima + disques** (table rase totale)
  ;
- `bootstrap/rollback.yaml` (rôle `k8s-rollback`) — ramène un nœud à « Debian nu
  ».

Conséquence : pour rejouer `ceph` from-scratch, il faut tout remonter (up +
bootstrap + …, ~15-50 min) alors qu'on ne voulait défaire que Ceph. Cette
asymétrie ralentit l'itération, surtout sur les phases **stateful et coûteuses**
(Ceph, datalake, CNPG) dont la mise en place prend le plus de temps.

Ce rollback est **distinct** du rollback **transactionnel** d'un rôle
([ADR 0050](0050-modele-reprise-role-ansible.md), `rescue:`/#236) : celui-là
**compense automatiquement** un pas qui _vient d'échouer_, au plus près de la
tâche, pour reprendre. Ici on veut un acte **volontaire, manuel, par phase** :
effacer **toutes les traces** d'une phase déjà montée (CRD, CR, namespaces, PVC,
données, état node-side) pour revenir à « avant cette phase ».

Cadrage qui **simplifie radicalement** le problème : le banc est **jetable**
([ADR 0035](0035-strategie-bancs-fidelite-vitesse.md)/[0038](0038-lima-seul-banc-local.md)).
Le rollback de phase est donc **destructif TOTAL** — il efface les données sans
distinction (PVC, buckets S3, bases). Aucun des garde-fous d'une désinstallation
**prod** (préserver/sauvegarder les données, `reclaimPolicy: Retain`, ordre fin
anti-deadlock de finalizers) n'est requis : c'est un outil de **banc**, pas une
procédure d'exploitation. La désinstallation prod fine reste documentée par les
RUNBOOK (cf. [storage/ceph/RUNBOOK.md](../../storage/ceph/RUNBOOK.md) §
Désinstallation), hors périmètre de cet ADR.

## Décision

**On dote le banc d'un rollback PAR PHASE, symétrique du montage, destructif
total, réservé au banc jetable.** Cinq règles.

### 1. Symétrie d'invocation

`bench/lima/run-phases.sh rollback <phase>` défait ce que
`run-phases.sh <phase>` a monté. La phase est nommée à l'identique (`ceph`,
`sc`, `datalake`, `metrics-server`, `monitoring`, `dataops`, `gitops`,
`gitops-seed`…). Couverture : **toutes les phases plateforme**.

### 2. Stratégie d'effacement — gros grain

On efface au **gros grain**, pas ressource-par-ressource : **namespace(s) + CRD
cluster-scoped + PVC + état node-side** de la phase. Ce choix est délibéré : le
delete chirurgical ordonné (OBC → CephObjectStore → CephCluster…) se heurte aux
**deadlocks de finalizers** documentés (RUNBOOK Ceph : OBC/store en `Deleting`
mutuel). Sur un banc jetable, on n'a pas à les ménager : on **force** les
finalizers récalcitrants (`patch metadata.finalizers=null`) puis on supprime.
L'état **node-side** que le delete Kubernetes ne couvre pas (disques Ceph,
`/var/lib/rook`) est nettoyé par les primitives dédiées
([storage/ceph/cleanup.sh](../../storage/ceph/cleanup.sh)).

### 3. Table de périmètre par phase

Chaque phase déclare **ce qu'elle a créé** → ce que son rollback efface. Le
périmètre vit dans le code (table phase → ressources), versionné, générique
([ADR 0023](0023-plateforme-exemple-generique.md)). Exemples (valeurs d'exemple)
: `ceph` → ns `rook-ceph` + CRD `*.ceph.rook.io` + disques `vd*` +
`/var/lib/rook` ; `dataops` → ns `postgres`/`dagster`/`marquez` + CRD
`postgresql.cnpg.io` ; `monitoring` → ns `monitoring` + CRD
`monitoring.coreos.com`.

### 4. Ordre inverse des dépendances

Un rollback de phase respecte l'**ordre inverse du montage** : on ne retire pas
Ceph (`ceph`) tant que `sc`/`datalake` (qui en dépendent) ne sont pas retirés.
Le rollback d'une phase **socle** signale (ou refuse) si une phase **aval** est
encore présente — pas de demi-état incohérent.

### 5. Banc-only, garde-fou explicite

Le rollback de phase **DÉTRUIT des données**. Comme le harnais d'arrêt injecté
(#236), il exige `BANC_JETABLE=1` et refuse de tourner sinon. Il vise
`KUBECONFIG`/inventaire **banc** (cible explicite,
[ADR 0053](0053-isolation-multi-cible-banc-prod.md)) — jamais la prod.

## Statut

Accepted. La mise en œuvre (table de périmètre, code `phase_rollback`, preuve
par cycle monte→rollback→remonte) est tracée par un plan d'implémentation
(`docs/plans/`) et des issues GitHub déclinées par phase.

## Conséquences

- **Gain** : itération **rapide** sur une phase isolée (défaire+rejouer une
  brique sans remonter tout le socle) ; symétrie lisible avec le montage (ADR
  0045). Particulièrement utile pour les phases stateful coûteuses (Ceph,
  datalake, CNPG).
- **Prix à payer** : une **table de périmètre par phase** à maintenir en phase
  avec ce que chaque rôle crée — un nouveau namespace/CRD non déclaré au
  rollback laisse un résidu. À tester par un cycle monte→rollback→**état propre
  vérifié** (un `state.sh`/healthcheck qui confirme l'absence de trace).
- **Garde-fou par destruction assumée** : ce rollback **efface les données**. Le
  `BANC_JETABLE=1` ferme l'usage par inadvertance ; il ne protège pas un
  opérateur qui le lance sciemment sur un banc qu'il voulait garder — c'est un
  outil de banc jetable, pas un filet.
- **Frontière maintenue** : ne remplace NI le `down` global (table rase VMs), NI
  `rollback.yaml` (Debian nu), NI la désinstallation **prod** fine des RUNBOOK
  (préservation des données, ordre anti-deadlock). Trois échelles distinctes :
  phase (cet ADR), nœud (`rollback.yaml`), banc (`down`).

## Alternatives écartées

**Delete chirurgical ordonné par ressource** (façon désinstallation prod du
RUNBOOK). Écarté pour le banc : complexe, exposé aux deadlocks de finalizers, et
inutilement prudent sur du jetable où l'on peut forcer. Reste la bonne approche
**en prod**, hors périmètre de cet ADR.

**Préserver les données par défaut** (`reclaimPolicy: Retain`, flag
`--purge-data`). Écarté : sur banc jetable, la donnée n'a aucune valeur ; le
garde-fou « préservation » serait du coût sans bénéfice. Réservé à une
éventuelle procédure prod.

**S'en remettre au `down` global** (statu quo). Écarté : remonter tout le socle
pour re-tester une seule phase est précisément la friction que cet ADR supprime.
