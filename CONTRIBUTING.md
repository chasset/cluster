# Contribuer à `cluster`

Outillage géré par [Lefthook](https://lefthook.dev/) (hooks git),
[Prettier](https://prettier.io/) (format),
[yamllint](https://yamllint.readthedocs.io/),
[shellcheck](https://www.shellcheck.net/),
[kubeconform](https://github.com/yannh/kubeconform) et
[ansible-lint](https://ansible-lint.readthedocs.io/). Les messages de commit
suivent la convention
[Conventional Commits](https://www.conventionalcommits.org/).

## Règle fondatrice — dépôt multi-topologies, valeurs génériques

Ce dépôt est un **catalogue de topologies d'infrastructure** (mono-nœud,
multi-nœuds, bare-metal hyperconvergé…) : **plusieurs infra déclarées, une seule
activée** par déploiement — à la manière de Pulumi/Terraform — pas
l'infrastructure réelle d'un contributeur
([ADR 0023](docs/decisions/0023-plateforme-exemple-generique.md)). **Tout ce qui
est versionné — code, manifestes, scripts ET prose (docs, ADR, RUNBOOK) —
emploie des valeurs d'exemple génériques**, jamais les valeurs réelles d'un
déploiement (qui vivent dans une config locale non versionnée).

- **À génériser** : IP / plages réseau (→ p. ex. `10.0.0.0/22`), noms de nœuds /
  hôtes / PVC / buckets (→ `cp1`, `node1`…), noms d'organisation / sites (→ «
  l'organisation »), **cas d'usage métier propres à un projet** (sources de
  données, services applicatifs spécifiques → « source de données ouverte », «
  backend d'auth »…).
- **À GARDER** : les logiciels / bases qui _portent_ une décision (briques
  d'infra que le dépôt propose : Ceph, MySQL, Cilium, cert-manager, Argo CD…) —
  les occulter viderait l'ADR de son sens. _Garder ce que le dépôt propose comme
  brique ; génériser ce qui n'a de sens que pour une instance._
- **Valeur d'exemple _concrète_**, pas tournure vague (un `/22` ≠ un `/24`) ; le
  contexte chiffré qui fonde une décision est conservé.
- **Spécificités réelles** = fichier de config **local non versionné**
  (gitignoré) surchargeant un **`*.example` versionné** — voir la convention
  `.env` / `.env.example` et les inventaires de banc.
- **Exceptions** : le réseau d'exemple du banc local (`192.168.67.0/24`) reste
  tel quel (exemple fonctionnel public) ; l'historique de validation banc
  (`test/RESULTS.md`) n'est **pas** réécrit (honnêteté des Runs).

## Traçabilité : ADR, audits, plans

Quatre natures d'écrits, quatre rôles non chevauchants — **un ADR DÉCIDE, un
plan MET EN ŒUVRE, une issue EXÉCUTE, une PR LIVRE**
([ADR 0057](docs/decisions/0057-gouvernance-documentaire-adr-plan-issue.md)) :

| Trace     | Où                | Rôle                                                                                                                                       |
| --------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **ADR**   | `docs/decisions/` | **Décide** (le _pourquoi_) — structurante, numérotée, **immuable**.                                                                        |
| **Plan**  | `docs/plans/`     | **Met en œuvre** une décision (paliers + suivi) — thématique, **vivant**.                                                                  |
| **Issue** | GitHub            | **Exécute** — unité de travail fermable.                                                                                                   |
| **PR**    | GitHub            | **Livre** un changement + sa preuve, ferme une issue / coche un palier.                                                                    |
| **Audit** | `docs/audit/`     | **Mesure** l'écart à un standard — grille permanente + passages datés ([ADR 0058](docs/decisions/0058-doctrine-audit-grille-passages.md)). |

**Le test de découpe (par temporalité,
[ADR 0057](docs/decisions/0057-gouvernance-documentaire-adr-plan-issue.md))** :
un contenu **immuable** va dans l'ADR (« vrai dans 2 ans, sauf superseded ? ») ;
un **ordre de marche évolutif** dans un plan (« vais-je réordonner / cocher ça ?
») ; une **unité fermable** dans une issue.

Règles :

- **Un ADR avec mise en œuvre échelonnée ⇒ un plan dédié OBLIGATOIRE.** Jamais
  de tableau de paliers, checklist ou « TODO » **dans** un ADR (un ADR est
  immuable, un déroulé évolue). Un ADR purement conceptuel peut n'avoir aucun
  plan. Le plan **référence l'ADR qui le fonde** en en-tête.
- **Plans THÉMATIQUES et vivants** : `plan-<thème>.md` (pas daté). Chaque plan
  porte une section **« Suivi »** : paliers (cases à cocher), **issues créées**
  (liens `#NNN`), **état d'achèvement** global, renvoi aux runs de preuve
  (`RESULTS.md`). Le plan est le **tableau de bord** d'une décision.
- **Audit = grille permanente + passages datés**
  ([ADR 0058](docs/decisions/0058-doctrine-audit-grille-passages.md)) : la
  grille (dimensions/critères/méthode) ne périme pas ; un passage est daté
  (`AAAA-MM-JJ`), append-only, **renvoie aux ADR** pour les _pourquoi_, et ses
  manques deviennent des **issues**.
- **Audit de session** (figé : journal d'un moment — réalignement de branche,
  dette) reste daté : `AAAA-MM-JJ-audit-<sujet>.md`. À distinguer d'un **plan
  vivant**.
- **Frontière ADR 0023** : `docs/plans/` ne versionne que des **plans d'INFRA**
  (socle générique). Un plan **métier / applicatif** vit dans le dépôt
  applicatif (`atlas`), **pas ici**.
- **Numéro d'ADR = ressource partagée** entre branches parallèles : en cas de
  collision (deux features réservant le même numéro), renuméroter au rebase et
  corriger l'index + toutes les références.
- Détail et index : [`docs/plans/README.md`](docs/plans/README.md).

## Installation des outils

```bash
pnpm install                                         # installe lefthook + prettier + commitlint
brew install yamllint shellcheck kubeconform ansible-lint
```

`pnpm install` exécute automatiquement `lefthook install` qui pose les hooks git
(pre-commit, pre-push, commit-msg).

## Commandes utiles

```bash
pnpm format         # applique Prettier
pnpm lint           # vérifie format + yaml + shell
pnpm lint:k8s       # valide les manifests via kubeconform
pnpm lint:ansible   # lint les playbooks Ansible
pnpm release        # bump version + met à jour CHANGELOG + crée tag git
pnpm release:dry    # aperçu de la prochaine release sans rien modifier
```

## Workflow de PR

- Branche : `<type>/<courte-description>` (ex. `feat/etcd-backup`,
  `fix/state-passwd-locale`).
- Commits : Conventional Commits, sujet en minuscule, corps ≤ 100 colonnes. Pas
  d'email dans le message (le hook `no-emails` rejette).
- Avant de pousser : les hooks `pre-push` (yamllint, shellcheck, kubeconform,
  prettier, ansible-lint) doivent passer. `pnpm install` les pose
  automatiquement.
- Ne pas pousser directement sur `main` — le hook `no-direct-push-to-main`
  l'interdit ; passer par une PR.

### Merge & traçabilité (squash)

Le dépôt merge **en squash uniquement** (`squash and merge`). Conséquence : la
PR entière devient **un seul commit** sur `main`, dont le **message = le titre
de la PR** (et le corps = la liste des commits de la branche). Le `main` reste
linéaire et lisible (1 PR = 1 commit), mais cela impose une discipline :

- **Le titre de PR EST le commit de `main`** → il doit être un Conventional
  Commit valide (`feat(scope): …`, minuscule, sans `(#issue)`). Un job CI le
  valide (`commitlint` sur le titre) : le squash le propage tel quel à `main`,
  donc à release-please et au `CHANGELOG`.
- **1 PR = 1 type/scope cohérent** = **1 ligne de `CHANGELOG`**. Le squash
  n'expose qu'**un** préfixe au changelog ; mélanger deux features distinctes
  dans une PR en cache une. Les `docs:`/`test:` qui _servent_ la feature peuvent
  l'accompagner ; deux capacités indépendantes → deux PR.
- **Lier les issues via `Closes #N` dans la _description_ de PR**, pas dans le
  corps des commits (le squash les enfouit ; GitHub n'auto-fermerait pas). C'est
  ce qui ferme l'issue au merge et garde le lien commit↔issue durable.
- **Pas de `(#issue)` dans le titre** : le squash ajoute déjà `(#PR)`. En mettre
  un produit un double numéro parasite (`… (#157) (#144)`).
- Les commits _internes_ à la branche peuvent rester atomiques (utile à la
  revue) — ils sont aplatis au merge, donc leur granularité ne survit pas sur
  `main`. Si cette granularité doit survivre (revert/bisect fins), **scinder en
  plusieurs PR** plutôt que compter sur le squash.

## Validation locale complète

```bash
pnpm format:check                       # prettier
yamllint -c .yamllint.yaml .            # lint YAML
find . -name '*.yaml' \
  -not -path './bootstrap/*' -not -path './node_modules/*' \
  -not -path './storage/ceph/crds.yaml' -not -path './storage/ceph/common.yaml' \
  -not -path './storage/ceph/operator.yaml' -not -path './storage/ceph/cluster.yaml' \
  -not -path './storage/ceph/dashboard.yaml' -not -path './storage/ceph/toolbox.yaml' \
  -not -path './platform/k8s-dashboard/values.yaml' \
  | xargs kubeconform -strict -ignore-missing-schemas \
      -schema-location default \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
ansible-lint bootstrap/
shellcheck $(find . -name '*.sh' -not -path './node_modules/*')
```

## Tests

Voir [`test/`](test/) — banc **Lima** pour valider sur Debian 13 arm64 avant de
toucher les serveurs (seul banc local,
[ADR 0038](docs/decisions/0038-lima-seul-banc-local.md)) :

- [`test/lima/`](test/lima/) — banc multi-nœuds, profils léger (~11 min) et Ceph
  (~30 min), via [`run-phases.sh`](test/lima/run-phases.sh) à gates. Exerce le
  multi-VM + Rook-Ceph + la chaîne DataOps.

Résultats du dernier banc : [`test/RESULTS.md`](test/RESULTS.md).

## Versionnement (release-please)

Le versionnement est **automatique** via le workflow
[`.github/workflows/release.yml`](.github/workflows/release.yml) qui utilise
[release-please](https://github.com/googleapis/release-please).

À chaque push sur `main`, release-please :

1. Parcourt les commits depuis le dernier tag ;
2. Calcule le prochain semver à partir des préfixes Conventional Commits
   (`feat:` → minor, `fix:`/`perf:` → patch, `feat!:` ou `BREAKING CHANGE:` →
   major) ;
3. Crée (ou met à jour) une **PR de release** intitulée `chore(release): vX.Y.Z`
   qui contient :
   - bump de `package.json` ;
   - mise à jour du `CHANGELOG.md` ;
   - mise à jour du `.release-please-manifest.json`.

Quand vous mergez cette PR, release-please pousse le tag `vX.Y.Z` et crée une
[GitHub Release](https://github.com/univ-lehavre/cluster/releases) avec le
changelog généré. Aucun bump manuel à faire.

Le script `pnpm release` (commit-and-tag-version) reste disponible pour un bump
manuel hors workflow GitHub, mais ce chemin doit rester exceptionnel — la source
de vérité est release-please.

## Code de conduite

La participation au projet est régie par notre
[code de conduite](CODE_OF_CONDUCT.md). En contribuant, vous vous engagez à le
respecter.

## Toute page Markdown est atteignable

Tout fichier `*.md` versionné doit être **atteignable depuis la documentation**
: présent dans le sidebar VitePress ou cible d'un lien depuis une page elle-même
atteignable ([ADR 0029](docs/decisions/0029-markdown-atteignable-doc.md)). Le
garde-fou `pnpm lint:docs-orphans`
([`scripts/check_md_orphans.py`](scripts/check_md_orphans.py)) échoue sur tout
orphelin — il tourne dans `pnpm lint` et en CI.
