# 0077 — `cluster next` : menu des couches montables (dépendances réelles vs convention d'ordre)

## Statut

Accepted (2026-06-16)

Étend `cluster next` ([ADR 0063](0063-ansible-runner-boucle-p5.md)) en
s'appuyant sur le **graphe atomique unique**
([ADR 0066](0066-rollback-atomique-graphe-composants.md)) comme source de vérité
des dépendances. Reste borné par le modèle déclaratif
([ADR 0056](0056-modele-declaratif-topologies.md)) et la dérivation de couches
([ADR 0069](0069-topology-layers-dag-grain-phase.md)).

## Contexte

`cluster next` montait jusqu'ici **la première couche manquante** de la séquence
du chemin (parité `state.sh` : le « 1er drift »). La séquence d'un chemin
(`expected_phase_sequence`) est un **ordre total** — une transcription fidèle
des arms de `run-phases.sh`. Or cet ordre mêle **deux natures** de contraintes :

- de **vraies dépendances** : les apps consomment du stockage (`gitea`,
  `prometheus` montent des PVC) → `monitoring`/`gitops` **dépendent** de
  `storage-simple` ;
- de simples **conventions de montage** : la couche stockage est placée **en
  tête** de la queue applicative « même quand le consommateur n'en dépend pas »
  (`layers.py:resolve_layers`, partition stable storage-first). Ainsi
  `storage-simple` précède `metrics-server` **alors que `metrics-server` n'a
  aucune dépendance de stockage** (ADR 0069 — c'est le cœur de cet ADR-là).

Conséquence : on ne pouvait pas monter `metrics-server` **avant**
`storage-simple`, sans aucune raison technique — seulement parce que `next` ne
proposait que le premier de l'ordre conventionnel. L'opérateur n'avait pas la
main sur l'ordre de deux couches pourtant **indépendantes**.

## Décision

**`cluster next` propose en MENU toutes les couches montables MAINTENANT** —
celles dont **toutes les dépendances RÉELLES** (graphe atomique, ADR 0066) sont
déjà satisfaites — et **l'opérateur choisit** laquelle monter ; le premier de
l'ordre du chemin reste le **défaut**. Quatre points.

### 1. « Montable » se lit du graphe RÉEL, pas de l'ordre conventionnel

Une couche est montable si elle est manquante (`diff_phases`) **et** qu'aucune
de ses dépendances n'est elle-même manquante. Les dépendances sont **dérivées du
graphe atomique** (`layers.phase_deps`, qui projette
`component_deps`/`phase_of_component` de `rollback-lib.sh` au grain phase) —
**pas** de l'ordre des arms. On ne code **aucun** second graphe en Python (ADR
0066 §invariant 3) : la convention storage-first de `resolve_layers` reste le
**défaut affiché** (premier de la liste), mais **n'interdit plus** un autre
ordre. Ainsi `metrics-server` et `storage-simple`, sans arête entre eux, sont
**tous deux** proposés après le socle.

### 2. L'amont (VMs, socle k8s) est un prérequis DUR — jamais un menu

`up` (créer les VMs) et `bootstrap`/`bootstrap-ha`/`join-cp` (amorçage k8s) sont
des prérequis de **tout** le reste. Tant qu'une de ces phases manque, c'est la
**seule offre** — on ne « choisit » pas entre créer les VMs et monter une couche
applicative. Le menu ne concerne que la **queue applicative** (couches dont
l'amont est fait).

### 3. Façade fine, cœur PUR (ADR 0049/0063)

- `plan.installable_now(...)` est **pur** : il ne shelle pas. Il reçoit un
  **fournisseur paresseux** de la carte de dépendances (`deps_fn`) que la façade
  branche sur `layers.phase_deps`. Il ne l'invoque **qu'au-delà du garde-fou
  amont** (inutile de consulter le graphe pour décider de créer les VMs ; et
  cela garde `plan.py` sans subprocess, ADR 0063 G5).
- Repli **sûr** : `deps_fn` absent → comportement historique « 1er drift » seul
  (au plus une couche). Sans la carte, on **ne présume jamais** l'indépendance
  de deux couches.

### 4. Choisir au menu VAUT décision — pas de double confirmation

Sélectionner un numéro dans le menu **est** la décision humaine explicite (G2,
ADR 0063). On ne redemande **pas** de confirmation `[o/N]` ensuite : un seul
geste, pas de friction redondante. Le chemin **mono-couche** (une seule couche
montable) conserve la confirmation `[o/N]` — elle y est l'unique garde-fou avant
de muter le banc. Hors-TTY / `--yes` : le menu prend le **défaut** sans prompter
(CI).

## Conséquences

- L'opérateur monte les couches **indépendantes dans l'ordre qu'il veut**
  (`metrics-server` avant `storage-simple`, p. ex.) sans contournement, tout en
  étant **empêché** de monter une couche dont une vraie dépendance manque (le
  graphe garde la cohérence).
- La distinction **dépendance réelle ↔ convention d'ordre** est désormais
  **agie**, pas seulement documentée (ADR 0069) : le menu n'expose que les
  arêtes réelles du graphe atomique.
- Aucune duplication de graphe (ADR 0066 préservé) : `phase_deps` **projette**
  le graphe existant ; le défaut du menu **reste** l'ordre des arms
  (`resolve_layers`), donc `test_parity` n'est pas affecté.
- Preuve ([ADR 0034](0034-validation-e2e-from-scratch.md)/0052) : `phase_deps`
  est testé **contre le vrai graphe bash** (`test_layers`, pas un stub) — il
  prouve que `storage-simple`/`metrics-server` sont des racines indépendantes et
  que `monitoring`/`gitops`/`dataops`/`gitops-seed` portent leurs vraies arêtes.
  `installable_now` est testé **purement** (carte figée == dérivée) ; le menu
  est testé en **façade** (TTY stubé : choix d'un numéro → couche montée, pas de
  double `[o/N]`).

## À revoir si

- Une couche acquiert une dépendance **non exprimable** par le graphe atomique
  (p. ex. un ordre imposé par une raison externe au DAG) → l'ajouter au graphe
  (source unique), **pas** un cas particulier dans `installable_now`.
- Le menu devient trop large (beaucoup de couches indépendantes simultanées) au
  point de nuire à la lisibilité → envisager un regroupement, mais **sans**
  remasquer un choix d'ordre légitime.

## Alternatives écartées

- **Garder « 1er drift » seul** (statu quo) : interdit `metrics-server` avant
  `storage-simple` sans raison technique. C'est précisément ce que cet ADR
  corrige.
- **Coder un graphe phase→phase en Python** pour décider de l'indépendance :
  recrée le double-graphe que
  l'[ADR 0066](0066-rollback-atomique-graphe-composants.md) a supprimé. Rejeté —
  `phase_deps` **projette** le graphe atomique, n'en invente aucun.
- **Monter toutes les couches montables d'un coup** : retire le contrôle
  pas-à-pas (un `next` = une couche, ADR 0063) et l'ordre choisi par
  l'opérateur. Rejeté — le menu préserve « un geste, une couche ».
- **Lever la convention storage-first de `resolve_layers`** (re-trier le DAG) :
  changerait l'ordre **par défaut** et romprait la parité avec les arms
  (`test_parity`). Rejeté — la convention reste le **défaut** ; le menu ne fait
  qu'**autoriser** un autre ordre, sans changer celui proposé en premier.
