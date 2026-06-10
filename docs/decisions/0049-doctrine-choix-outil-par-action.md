# 0049 — Doctrine du choix d'outil par action (pondérée)

## Contexte

Le dépôt est devenu **polyglotte de fait** : bash (orchestration de CLIs
kubectl/ceph/ssh, ~53 scripts), `jq` (parsing JSON), Python
(`uv`/`ruff`/`pytest` pour la logique non triviale), bats (fonctions bash
pures), **Ansible** (63 invocations `kubernetes.core.k8s` dans 12 rôles
`platform-*`, plus tout le bootstrap nu), et un résidu **Perl**
(`bootstrap/security/blur-env.pl`). Or aucun ADR ne dit **quel outil pour quelle
action ni à quel prix**.

L'[ADR 0017](0017-langage-des-scripts.md) formalise bash/jq/Python/bats/Node et
ferme la porte à Go, mais il est **antérieur à l'adoption massive d'Ansible** :
il ne mentionne ni Ansible comme langage de plein droit, ni Perl (le
`blur-env.pl` n'a jamais été justifié face à Python), et il oppose les langages
**deux à deux** (« bash vs Python ») au lieu de poser un **cadre de décision
pondéré**.

L'[ADR 0033](0033-orchestration-ansible-platform-dataops.md) a porté la couche
plateforme DataOps en rôles Ansible, mais son périmètre est aujourd'hui
**partiellement périmé** : il déclare le monitoring « hors périmètre,
best-effort du shell » alors qu'un rôle `platform-monitoring` + un playbook
`bootstrap/monitoring.yaml` existent désormais ; et il ne porte Ceph qu'à moitié
(le rôle `ceph-pre-install` côté nœuds existe, mais les CRs Rook/Ceph **côté
cluster** restent posés en shell via `storage/ceph/*` + `run-phases.sh`).

Conséquence : le polyglottisme n'est **pas gouverné**. Un contributeur ne sait
pas si une nouvelle brique va en shell, en Ansible ou en Python, ni à quel coût
de diversité — d'où des incohérences vérifiées : `check_mode` absent partout,
des briques encore en shell sans critère explicite (Ceph cluster,
metrics-server, StorageClasses/datalake, CRDs Gateway API + CRs `cilium-expo`),
et un `blur-env.pl` en Perl pur sans justification.

## Décision

**On choisit le meilleur outil _par action_ (par catégorie de tâche), pondéré
par le coût de diversité.** Chaque langage supplémentaire a un prix (lisibilité,
maintenance, toolchain, testabilité) ; on ne maximise donc pas l'optimalité
locale de chaque script, on optimise le couple (adéquation outil↔action,
cohérence de l'ensemble). Un outil légèrement sous-optimal mais déjà maîtrisé
bat un outil parfait mais isolé.

Cette doctrine **supersede l'[ADR 0017](0017-langage-des-scripts.md)** (qu'elle
reprend intégralement et étend : Ansible promu langage de plein droit, Perl
traité, cadre de pondération ajouté) et **amende
l'[ADR 0033](0033-orchestration-ansible-platform-dataops.md)** (correction de
périmètre, cf. Conséquences).

### Outil par défaut, par catégorie d'action

| Catégorie d'action                                                                                                                          | Outil                                                                         | Pourquoi                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Convergence d'état sur des nœuds + apply Kubernetes idempotent** de la couche **plateforme** (addons, opérateurs, CRDs, manifestes figés) | **Ansible** (`kubernetes.core.k8s`/`k8s_info`)                                | Idempotence, `check_mode`, `changed_when`, handlers, `server_side_apply`, gates `until`/`k8s_info`, secrets dérivés sont **natifs** ; les réimplémenter en shell reproduit les drifts L12–L20 qu'a supprimés l'ADR 0033. 63 invocations dans 12 rôles le confirment. |
| **Bootstrap NU** (kubeadm, CRI, init/join/rollback, AVANT que le cluster existe)                                                            | **bash + `kubectl` sans collection**                                          | Choix délibéré (ADR 0033 §2 : « zéro dépendance collection » avant le cluster) — vérifié : 0 usage `kubernetes.core` dans les rôles `k8s-*`. La catégorie ci-dessus **ne s'y applique pas**.                                                                         |
| **Orchestration de CLIs externes** (kubectl/ceph/ssh, helpers de banc, hooks git, pré-accès SSH)                                            | **bash** (`set -euo pipefail`, shellcheck 0)                                  | Cœur d'orchestration (ADR 0017 inchangé). Adéquation maximale, lisibilité néophyte, coût de réécriture nul à conserver. On ne porte pas le bash qui marche par opportunisme.                                                                                         |
| **Scénarios e2e / chaos** (injection de pannes sur banc, ADR 0025/0034)                                                                     | **bash**                                                                      | Orchestration de CLIs destructifs ponctuels sur le banc, même nature que `cleanup.sh`. La logique de décision isolable part en bats.                                                                                                                                 |
| **Surcharge d'un manifeste figé** (`helm template` vendored)                                                                                | **patch strategic-merge `kubernetes.core.k8s`**, **JAMAIS** un `.j2` du rendu | Hisse l'ADR 0033 §3 en doctrine : emballer un rendu de ~700 lignes en Jinja diverge du rendu et perd les retouches documentées. Le choix d'outil pour CETTE action est le patch ciblé.                                                                               |
| **Parsing de sorties structurées**                                                                                                          | **jq** (sur `-o json`/`-f json`)                                              | Jamais awk/grep/cut sur des sorties humaines. Inchangé.                                                                                                                                                                                                              |
| **Logique non triviale** (structures, graphes, validation au-delà de jq, calculs)                                                           | **Python** (`uv`+`ruff`, tests pytest)                                        | Second langage de plein droit (ADR 0017, amendement 2026-06-07). Repreneur naturel de `blur-env.pl`.                                                                                                                                                                 |
| **Comportement des fonctions bash pures**                                                                                                   | **bats** (`test/unit/`, libs `bootstrap/lib/`)                                | shellcheck valide la syntaxe, bats le comportement. Un code de logique sans test n'est pas mergeable.                                                                                                                                                                |
| **Runtime d'outils de dépôt** (site doc, lint, hooks)                                                                                       | **Node** (VitePress/prettier/commitlint/jscpd/lefthook)                       | N'est **pas** un langage de script applicatif : un nouveau besoin de logique va en Python.                                                                                                                                                                           |
| **Masquage `.env` → `.env-example`** (cas `blur-env.pl`)                                                                                    | **Perl — EN SURSIS → Python**                                                 | Perl n'apporte aucune adéquation supérieure (texte ligne-à-ligne, trivial en Python) et son coût de diversité est maximal (aucun autre Perl, pas de toolchain/test). C'est une **dette à porter**, pas un précédent : **aucun nouveau Perl**.                        |
| **Langage compilé (Go/Rust)**                                                                                                               | **exclu**                                                                     | Coût de diversité prohibitif, aucun binaire à distribuer, public néophyte. Le gain d'adéquation n'excède jamais le coût.                                                                                                                                             |

### Critères de pondération (arbitrent les cas limites)

Dans l'ordre de priorité décroissant :

1. **Adéquation native** de l'outil à l'action (fait-il _nativement_ ce que
   l'action exige : idempotence, parsing JSON, convergence d'état). _Critère
   premier._
2. **Gestion native des secrets/identités** quand l'action en manipule (un
   secret dérivé à source unique est natif en Ansible — leçon L16/L17 ; argument
   des ADR 0003/0011/0023).
3. **Coût de réécriture** : un outil qui marche déjà ne se réécrit pas par
   opportunisme (pondère fortement contre tout portage gratuit).
4. **Cohérence avec l'existant** : préférer un outil déjà présent et outillé ;
   chaque langage neuf paie un coût de diversité.
5. **Lisibilité néophyte** : inspectable sans toolchain lourde (favorise
   bash/jq, pénalise Perl/Go).
6. **Testabilité** : existe-t-il un cadre de test (bats / pytest) — non
   négociable.
7. **Contexte d'exécution** : sur des nœuds pilotés → Ansible ; enchaînement
   local de CLIs → bash ; calcul/données → Python.
8. **Performance** — **critère secondaire** : n'entre en compte que si un écart
   est **effectivement mesuré et significatif** ; ne prime jamais sur
   l'adéquation, la lisibilité ou la testabilité sur la seule base d'une
   intuition de rapidité (le garde-fou contre « Go parce que c'est plus rapide
   »).

### Exceptions — restent délibérément en bash

`cni.sh` (orchestration du CLI `cilium` + pose de CRs, tourne dans la VM sans
repo) ; `state.sh` / `report.sh` (diagnostic lecture seule multi-couches —
Ansible = convergence, pas reporting) ; `cleanup.sh` (wipe destructif lancé
consciemment) ; `first-access.sh` (pré-accès SSH **avant** qu'Ansible puisse
piloter) ; `gitea-init.sh` (étape de **données** post-bootstrap, ADR 0044) ; les
tests bats / `*-assert.sh` ; le harnais de banc jetable et l'émetteur
OpenLineage (outillage e2e, pas une brique plateforme — ADR 0033 §5).
**Mailpit** est dans cette catégorie : c'est un **puits SMTP de test du banc**
(« pas déployé en prod », cf. `platform/mailpit/README.md`), pas une brique
plateforme à porter.

### Intrinsèquement manuel (hors de tout langage de script)

Install ISO Debian, partitionnement interactif, diagnostic firmware console →
relèvent de preseed/PXE, hors périmètre.

## Statut

Accepted. Supersede l'ADR 0017 ; amende l'ADR 0033.

## Conséquences

- **Édition de l'index et des statuts** (artefacts concrets) : ajouter cet ADR à
  [`docs/decisions/README.md`](README.md), y passer l'ADR 0017 en « Superseded
  by 0049 », et poser un en-tête « Superseded by 0049 » dans
  [`0017-langage-des-scripts.md`](0017-langage-des-scripts.md). Mettre à jour la
  référence du cadre dans `CLAUDE.md`.
- **Corrections de prose périmée** (conséquence de l'amendement ADR 0033) :
  [ADR 0026](0026-orchestration-dagster.md):17 et
  [ADR 0028](0028-orchestration-openlineage-marquez.md):19 disent « déployé par
  `kubectl apply` comme les autres addons » — **inexact** depuis que
  `platform-dagster` et `platform-marquez` sont des rôles Ansible. À corriger.
- **Portages déclenchés** (chacun **banc-requis** — un nouveau rôle qui
  s'applique sur un cluster change le comportement de déploiement et se
  re-prouve par un run, ADR 0034) : Ceph côté cluster, metrics-server,
  StorageClasses/datalake, CRDs Gateway API + CRs `cilium-expo`. Suivis par
  l'épopée #262. **Invariant** : un portage **retire** sa source shell (la
  `phase_*` de `run-phases.sh`, le heredoc `cni.sh`) une fois le rôle prouvé —
  il ne la **double** pas.
- **Bénéfice** : un contributeur sait, par catégorie d'action, quel outil
  retenir et pourquoi. **Prix** : la doctrine n'élimine pas le polyglottisme,
  elle le gouverne (le coût de diversité reste réel). **Garde-fou** : aucun
  nouveau langage (Go, nouveau Perl) sans démonstration que le gain d'adéquation
  excède le coût.
- **Doctrines sœurs** : la manière d'écrire les tâches (options natives) et le
  modèle de reprise/transactionnalité d'un rôle font l'objet des ADR
  [0051](0051-options-natives-ansible.md) et
  [0050](0050-modele-reprise-role-ansible.md), qui **réfèrent** au patron de
  rôle posé ici plutôt que de le redéfinir.
