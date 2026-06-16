# 0063 — `ansible-runner` pour la boucle « suggère → lance » (P5)

## Statut

Accepted (2026-06-13)

## Contexte

L'outil déclaratif ([ADR 0056](0056-modele-declaratif-topologies.md)) avance par
paliers (`plan-modele-declaratif.md`). **P0 à P4 sont livrés** : ils
**modélisent, génèrent, dérivent, exposent, filtrent et consignent** — toutes
des opérations **read-only** ; aucune ne lance de playbook. Le palier **P5**
introduit la première façade qui **orchestre** réellement : la boucle
**`diff → suggère → lance`** que
l'[ADR 0056 §2](0056-modele-declaratif-topologies.md) décrit (lire l'état voulu,
calculer ce qui manque, **lancer** le bon play).

L'ADR 0056 a **décidé la vision** (outil Python, `ansible-runner`, trois
façades) ; il restait à **acter l'ajout effectif de la dépendance**, qui n'est
pas encore dans `pyproject.toml` (aujourd'hui : `pyyaml`, `kubernetes`,
`certifi`, `jinja2`). Le dépôt exige qu'une dépendance structurante soit
**justifiée par un besoin réel** (« pas de dépendance avant le besoin »,
[ADR 0049](0049-doctrine-choix-outil-par-action.md) /
[ADR 0061](0061-posture-adoption-bonnes-pratiques.md)) et **tracée par une
décision** ([ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) : l'ADR
décide, le plan met en œuvre). C'est l'objet de cet ADR.

## Décision

**`ansible-runner` est adopté comme dépendance runtime ; `textual` est
différé.**

1. **`ansible-runner` (adopté).** P5 pilote les playbooks `bootstrap/*.yaml`
   depuis Python avec des **résultats structurés** (`rc`, `status`, events). La
   lib Python **officielle d'Ansible** est le bon outil pour ça
   ([ADR 0049](0049-doctrine-choix-outil-par-action.md), catégorie «
   orchestration ») :
   - elle **ne contredit aucun ADR Accepted** — elle **applique** l'ADR 0056 §2
     ;
   - elle a un **gain net** face à l'alternative (un `subprocess` + parse de la
     sortie de `ansible-playbook` — précisément le motif fragile que l'ADR 0056
     combat) ;
   - son **coût de diversité est faible** : écosystème Ansible déjà natif du
     dépôt (`kubernetes.core`, `ansible.cfg`, rôles), **zéro 6ᵉ langage**.

   Épinglée dans `uv.lock` (esprit
   [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)).

2. **`textual` (différé).** P5 commence par une **boucle CLI simple**
   (sous-commande `next` + `--apply`). Le **TUI riche** (`textual`/`rich`) reste
   **optionnel et hors P5** : la boucle informative ne l'exige pas
   ([ADR 0049](0049-doctrine-choix-outil-par-action.md) « pas de dépendance
   avant le besoin » ; l'ADR 0056 cite `textual` en **illustration**, pas en
   exigence). Une décision ultérieure l'actera si un vrai besoin d'UX
   interactive émerge.

### Garde-fous

- **G1 — pas de réimplémentation de convergence**
  ([ADR 0056 §7](0056-modele-declaratif-topologies.md)). `ansible-runner`
  **lance** ; le code Python **lit** les résultats exposés (`rc`, `status`,
  events). Il ne réimplémente **jamais** retry/backoff/idempotence ni un état
  réconcilié. **Consommer** un verdict exposé est permis ; le **dériver**
  (heuristique de temps, seuil maison) est interdit.
- **G2 — jamais d'auto-apply silencieux.** `next` (sans flag) **suggère** en
  texte ; `--apply` est une **décision humaine explicite** qui lance **une**
  phase. Pas d'enchaînement automatique de toute la séquence ; aucun lancement
  déclenché par la simple lecture.
- **G3 — chemin nommé codé**
  ([ADR 0045](0045-chemins-installation-banc-couches.md), CLAUDE.md). P5 **ne
  crée pas** un 2ᵉ chemin d'installation. La phase suggérée appartient à la
  séquence d'un **chemin nommé connu** ; `--apply` invoque le **même playbook**
  avec les **mêmes `-e` dérivés** (`derive_run_params`, P2) que `run-phases.sh`.
  L'ordre des phases est une **transcription fidèle** des arms de
  `run-phases.sh`, pas une réinvention.
- **G4 — non-régression byte-identique**
  ([ADR 0056 §3](0056-modele-declaratif-topologies.md)). P5 n'ajoute **que** de
  la convergence : elle ne touche ni la génération d'inventaire (P1), ni la
  dérivation (P2), ni les épreuves/historique (P4).
  `validate`/`generate`/`diff`/`status`/ `epreuves`/`runs` restent inchangés.
- **G5 — couche d'exécution isolée.** Le seul module qui importe
  `ansible_runner` est l'adaptateur `nestor/runner.py` (frontière pur/I-O nette,
  [ADR 0017](0017-langage-des-scripts.md)). Cela garde la porte ouverte à un
  autre moteur (l'ADR 0056 §7 a écarté Terraform/Pulumi pour raison technique,
  pas par couplage) et rend P5 **testable sans cluster** (l'adaptateur est
  _stubbé_ en CI ; la preuve réelle passe par un run de banc consigné,
  [ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md)).

## Conséquences

- `pyproject.toml` gagne **une** dépendance justifiée (`ansible-runner`),
  épinglée dans `uv.lock`. La lib `kubernetes` (déjà présente) suffit pour lire
  l'état réel — **aucune nouvelle dépendance d'état**.
- P5 devient actionnable : module pur `nestor/plan.py` (séquence attendue, diff,
  suggestion) + adaptateur `nestor/runner.py` + sous-commande `next`.
- Les tests P5 **_stubbent_** l'adaptateur (`launch_phase` monkeypatché) : aucun
  SSH ni cluster en CI. `ansible-runner` est une dépendance **runtime**, pas
  **exécutée** par la suite de tests.

### Alternatives écartées

- **`subprocess` + parse de `ansible-playbook`** : fragile (sortie humaine non
  contractuelle), exactement le motif que l'ADR 0056 combat.
- **`textual` d'emblée** : scope-creep — transformerait P5 en chantier d'UI
  alors que la boucle informative tient en CLI.
- **Tout en bash** : réimplémenterait l'orchestration que `run-phases.sh` porte
  déjà, à contre-courant de l'[ADR 0017](0017-langage-des-scripts.md) (Python
  dès que la logique se densifie).
