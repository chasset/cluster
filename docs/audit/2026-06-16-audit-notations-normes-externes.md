# 2026-06-16 — Audit « notations & normes externes applicables au dépôt (hors cyber) »

| Champ        | Contenu                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Date**     | 2026-06-16                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **Type**     | revue ciblée — quels **référentiels externes notés ou normalisés** (hors cybersécurité) s'appliquent à un dépôt d'IaC Kubernetes de recherche, et où le dépôt se situe sur chacun (preuves = fichier:ligne, sorties `grep`/`git`, ou absences par grep nul)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Fonde**    | _réflexion_ — alimente l'issue parapluie « manques actionnables » et de futurs ADR/plans. **Aucune décision ici.**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Prolonge** | le passage **notations cyber** du 2026-06-16 ([note sœur](2026-06-16-audit-notations-cyber.md), Scorecard/CIS/NIST-ANSSI) — qu'il **ne réécrit pas** : il prend les **autres familles** de référentiels (science ouverte, maturité DevOps/GitOps, conventions doc/versionnement, accessibilité/durabilité/legal). Recoupe aussi le passage de maturité #349 (DORA/MLOps/CNCF) sans le réécrire.                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Verdict**  | Le dépôt est **déjà fortement aligné mais rarement nommé** : SemVer/Keep-a-Changelog/Conventional Commits sont **explicitement câblés** ; FAIR est **revendiqué (manifeste) mais non mappé** ; Diátaxis est **décidé** ([ADR 0059](../decisions/0059-diataxis-typologie-documentation.md)). **Livrable : une rangée de badges au README, groupée par thématique** ([ADR 0080](../decisions/0080-notations-et-badges-readme.md)). **Exécuté dans la foulée** (cf. journal § État d'exécution) : badges Lot 0 posés ; Scorecard + CI câblés (workflows réels) ; mappings FAIR/OpenGitOps écrits ; a11y et REUSE **écartés** (gain net insuffisant, ADR 0061). Un audit a11y ponctuel a tout de même **trouvé un défaut réel** (#368). Manques de fond promus en issues : #366 (signature), #367 (SAST). **Aucun badge décoratif** (ADR 0080). |

## Pourquoi ce passage

La note sœur a traité les **notations cyber chiffrées**. Mais un dépôt d'IaC de
recherche est mesurable par d'**autres** familles de référentiels externes —
science ouverte, maturité d'ingénierie, conventions de versionnement,
accessibilité. Comme pour la cyber, chacune est lue à travers le **biais adoptif
borné** ([ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)) :
une norme n'a de valeur que si elle **mesure quelque chose de vrai** sur ce
dépôt précis, pas si elle empile un badge pour le badge. Les trois traits du
dépôt rappelés par la note cyber valent ici aussi (pas de production permanente
télémétrée ; compromis assumés tracés en ADR ; mono-mainteneur) — on ne les
répète pas.

Un quatrième trait conditionne ce passage-ci : le dépôt **revendique déjà des
cultures d'ingénierie** ([ADR 0062](../decisions/0062-cultures-ingenierie.md))
et tient un **inventaire de 94 bonnes pratiques**
([`bonnes-pratiques.md`](../architecture/bonnes-pratiques.md)). Ce passage ne
recense **pas** des pratiques internes (c'est le rôle de cette page) : il
confronte le dépôt à des **référentiels EXTERNES notés/normés**, et situe le
dépôt sur chacun, preuve à l'appui. La frontière est nette :
`bonnes-pratiques.md` dit « ce que le dépôt fait » ; ce passage dit « comment un
standard externe le noterait ».

Ce passage **ne crédite aucun palier au feeling** : chaque ligne cite une preuve
ouverte (fichier:ligne, `grep`, grep nul re-confirmé au 2026-06-16).

## Les référentiels applicables, par famille

### 1. Science ouverte & reproductibilité

#### 1.1 FAIR — Findable / Accessible / Interoperable / Reusable (mapping, pas une note)

FAIR est un **principe revendiqué** par le dépôt : le manifeste le cite
explicitement (réf. Wilkinson _et al._). Mais il n'est **mappé nulle part**
contrôle par contrôle — comme NIST CSF côté cyber, c'est un mapping contrôle →
preuve à produire, pas un score automatique.

| Facette FAIR      | Couverture de fait | Preuve                                                                                                              |
| ----------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| **Findable**      | forte              | DOI Zenodo concept (`CITATION.cff` `doi: 10.5281/zenodo.20287209`), badge DOI (`README.md:52`), dépôt public GitHub |
| **Accessible**    | forte              | dépôt public, `LICENSE` (MIT) + `NOTICE`, releases taguées, archive Zenodo pérenne                                  |
| **Interoperable** | moyenne            | formats ouverts (YAML/Markdown), `CITATION.cff` (vocabulaire CFF standard) ; pas de métadonnées schema.org/JSON-LD  |
| **Reusable**      | forte              | licence claire, `CITATION.cff` + provenance, ADR Nygard, manifeste — réutilisation documentée et citable            |

**Constat** : FAIR s'applique au **dépôt-en-tant-qu'objet-de-recherche** (code
citable), pas aux _données_ (qui vivent côté `atlas`, hors périmètre — cf.
gouvernance DataOps
[ADR 0041](../decisions/0041-gouvernance-completude-dataops.md)). Le dépôt est
**de fait largement FAIR** mais ne l'a jamais **constaté formellement**
(`grep -nE "\bFAIR\b"` hors manifeste/ADR 0061 = quasi nul).

**Effort : S (rédaction).** Une grille `docs/` FAIR→preuve (modèle du futur
mapping CSF côté cyber), sous doctrine
[ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md).

#### 1.2 OpenSSF Best Practices Badge (ex-CII) — santé projet OSS (note %, automatique)

Distinct du **Scorecard** (note /10 supply-chain, traité dans la note cyber) :
le **Best Practices Badge** est un auto-questionnaire ~70 critères (passing /
silver / gold) sur la santé _projet_ — change control, tests, docs, licence.
Très aligné avec le profil « projet de recherche tracé ».

| Critère Badge (échantillon)     | État au 2026-06-16 attendu | Preuve                                                                                                                                |
| ------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Licence FLOSS                   | **passing**                | `LICENSE` (MIT) + `NOTICE`                                                                                                            |
| Documentation de base           | **passing**                | `README.md`, `CONTRIBUTING.md`, site VitePress, 79 ADR                                                                                |
| Contrôle de version + CHANGELOG | **passing**                | Git, `CHANGELOG.md` (Keep a Changelog), release-please                                                                                |
| Build/test reproductibles       | **passing (partiel)**      | `pnpm lint`, banc Lima e2e ([ADR 0034](../decisions/0034-validation-e2e-from-scratch.md)) ; pas de « build » au sens applicatif (IaC) |
| Rapport de vulnérabilités       | **passing**                | `SECURITY.md` (Private Vulnerability Reporting)                                                                                       |
| Signature des releases          | **rouge**                  | tags non signés (cf. note cyber, check `Signed-Releases`)                                                                             |

**Effort : S.** Le badge se **remplit** (auto-déclaratif) ; le dépôt atteindrait
**passing** quasi immédiatement. `grep` `bestpractices` = **nul** → non câblé.

### 2. Maturité DevOps / SRE / GitOps

> Cette famille **recoupe** le passage de maturité #349 (DORA/MLOps/CNCF) et
> l'[ADR 0062](../decisions/0062-cultures-ingenierie.md) (cultures
> revendiquées). Ce passage n'en reprend **que l'angle « référentiel externe
> noté »**, sans réécrire ces sources.

#### 2.1 DORA / Four Keys — performance de livraison (4 métriques chiffrées)

Référentiel le plus connu (deployment frequency, lead time, change failure rate,
MTTR). **Problème de mesurabilité fondamental** : DORA mesure un **flux de
déploiement en production permanente** — or le dépôt est un **catalogue
bench-validé**, pas un cluster opéré télémétré
([ADR 0023](../decisions/0023-plateforme-exemple-generique.md)). Les quatre
métriques n'ont de proxys que partiels :

| Métrique DORA          | Proxy dans le dépôt      | Preuve / limite                                                                                                                                                                                      |
| ---------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deployment frequency   | cadence de release       | release-please quotidien, `CHANGELOG.md` (v2.36.0 au 2026-06-16) — mais « release » ≠ « déploiement prod »                                                                                           |
| Lead time for changes  | PR → merge → tag         | merge-commit ([ADR 0037](../decisions/0037-strategie-merge-commit.md)), CI 13 checks — mesurable via `gh`                                                                                            |
| Change failure rate    | **non mesuré**           | pas de prod télémétrée ; banc valide e2e mais ne compte pas d'« échecs en prod »                                                                                                                     |
| Time to restore (MTTR) | rollback prouvé sur banc | rollback par phase/atomique ([ADR 0054](../decisions/0054-rollback-par-phase-banc.md)/[0066](../decisions/0066-rollback-atomique-graphe-composants.md)) — **temps non chronométré en incident réel** |

**Constat** : DORA est **structurellement partiel** sur ce dépôt — non par
manque, mais par nature (pas de prod). À **ne pas câbler tel quel** : ce serait
mesurer un flux qui n'existe pas. `grep DORA` hors ADR 0062/inventaire =
**nul**.

#### 2.2 OpenGitOps (CNCF) — 4 principes GitOps (déclaratif / versionné / pull / réconcilié)

Le dépôt **revendique GitOps**
([ADR 0022](../decisions/0022-argocd-gitops-applicatif.md),
[`bonnes-pratiques.md`](../architecture/bonnes-pratiques.md) « GitOps ✅ »). Les
4 principes OpenGitOps sont un référentiel **qualitatif** (PASS/FAIL par
principe) :

| Principe OpenGitOps   | État                  | Preuve                                                                                    |
| --------------------- | --------------------- | ----------------------------------------------------------------------------------------- |
| Déclaratif            | **PASS**              | manifestes K8s, Argo CD Applications                                                      |
| Versionné & immuable  | **PASS**              | Git source de vérité, merge-commit, pas de push direct, images par digest (ADR 0006)      |
| Tiré automatiquement  | **PASS (applicatif)** | Argo CD + Gitea (pull) pour la couche applicative ; le bootstrap reste impératif (assumé) |
| Réconcilié en continu | **PASS (applicatif)** | Argo CD self-heal ; `bootstrap/state.sh` (drift 7 couches) côté infra                     |

**Effort : S (rédaction).** Mapping déjà **gagnable** : 4/4 sur la couche
applicative. `grep OpenGitOps` = **nul** (revendiqué « GitOps » sans citer le
référentiel CNCF). Une ligne dans `bonnes-pratiques.md` suffit.

#### 2.3 SRE (Google) — SLO / SLI / error budget

L'[ADR 0062](../decisions/0062-cultures-ingenierie.md) et
`bonnes-pratiques.md:46` notent déjà **SRE 🔶 partiel** : drift detection,
fraîcheur, etcd backup/RPO, rollback — **sans SLO/SLI/error-budget**. C'est un
**constat déjà tracé**, pas un manque nouveau. Sur réseau isolé sans télémétrie
de prod, un error-budget formel n'aurait pas d'assiette de mesure. **Rien à
câbler** ici ; pointer vers l'ADR 0062 suffit.

### 3. Conventions de documentation & de versionnement

C'est la famille où le dépôt est le **plus en avance** — référentiels souvent
**déjà cités nommément**.

| Référentiel externe        | État au 2026-06-16  | Preuve                                                                                                          |
| -------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Conventional Commits**   | **✅ câblé + cité** | commitlint (hooks lefthook + CI sur toute la plage), `CHANGELOG.md` cite le lien officiel                       |
| **SemVer**                 | **✅ câblé + cité** | release-please (`release-type: node`), `CHANGELOG.md` lie `semver.org`                                          |
| **Keep a Changelog**       | **✅ câblé + cité** | `CHANGELOG.md:3-4` cite `keepachangelog.com` ; généré par release-please                                        |
| **Diátaxis**               | **✅ décidé**       | [ADR 0059](../decisions/0059-diataxis-typologie-documentation.md) (typologie tuto/how-to/référence/explication) |
| **CITATION.cff (CFF 1.2)** | **✅ conforme**     | `CITATION.cff` `cff-version: 1.2.0` + DOI                                                                       |

**Constat** : sur cette famille, le dépôt **n'a quasiment rien à faire** — les
standards sont adoptés ET nommés. Seul **REUSE/SPDX** (cf. ci-dessous) manque
pour clore la conformité « licence machine-lisible ».

#### 3.1 REUSE / SPDX — conformité licence machine-lisible

Le dépôt a `LICENSE` + `NOTICE` + `CITATION.cff` (licence **humainement**
claire), mais **pas** d'en-têtes `SPDX-License-Identifier` par fichier ni de
structure `LICENSES/` REUSE. `grep "SPDX-License-Identifier\|REUSE"` = **nul**.

**Effort : M.** REUSE est **outillé** (`reuse lint` en CI) mais demande
d'annoter beaucoup de fichiers — **gain net discutable** pour un mono-dépôt
mono-licence (le critère 2
d'[ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md) : « le gain
dépasse-t-il le coût de la diversité ? »). **À évaluer, pas à adopter réflexe.**

### 4. Accessibilité, durabilité & legal

#### 4.1 WCAG 2.x — accessibilité du site VitePress (note A/AA/AAA)

Le dépôt **publie un site** (VitePress, `pnpm docs:build`). WCAG s'y applique :
contraste, navigation clavier, alternatives textuelles. **Aucun audit a11y**
n'existe (`grep "WCAG\|axe-core\|pa11y\|lighthouse"` = **nul**). VitePress
fournit une base raisonnable par défaut, mais **non vérifiée**.

**Effort : S.** Un job CI `pa11y-ci` ou Lighthouse-a11y (statique, non bloquant
d'abord) sur le site bâti. Pertinent pour le contexte universitaire (obligation
RGAA en France pour le secteur public — référentiel dérivé de WCAG).

#### 4.2 Green Software (SCI) — empreinte carbone logicielle

Le manifeste **évoque déjà** le décalage des charges selon l'intensité carbone
du réseau (`docs/manifeste.md:138`) et fait de la soutenabilité un axe. Mais il
n'existe **pas** de mesure SCI (Software Carbon Intensity) formelle. Sur un banc
arm64 éphémère, une note SCI aurait peu de sens ; c'est un **horizon revendiqué
sans référentiel chiffré**. **Rien à câbler** ; le manifeste porte déjà
l'intention.

#### 4.3 RGPD / RGAA — conformité legal

Le **trou RGPD** est **déjà le livrable gouvernance prioritaire** tracé par
[ADR 0041](../decisions/0041-gouvernance-completude-dataops.md) (qualification
DPO des datasets, rétention/minimisation/base légale). Ce passage **ne le rouvre
pas** : il **confirme** que le référentiel RGPD est connu et que le manque est
déjà une issue gouvernance. RGAA (accessibilité publique) rejoint le §4.1.

#### 4.4 ISO/IEC (27001 SMSI, 25010 qualité produit) — N/A pratique

`grep "ISO/IEC\|ISO 27001\|ISO 25010"` = **nul**. Ces normes visent une
**organisation** (27001) ou un **produit logiciel livré** (25010) — pas un
catalogue d'IaC de recherche mono-mainteneur. **Hors périmètre assumé** : les
mentionner pour acter qu'elles ont été **examinées et écartées** (pas oubliées),
conformément à la rigueur des « alternatives écartées ».

## Plan de remédiation — vers une rangée de badges honnêtes au README

> **Finalité concrète** de ce passage : faire passer le README d'**un seul
> badge** (DOI, `README.md`) à une **rangée** qui reflète les référentiels
> réellement adoptés. Règle d'or, héritée de la posture « ne créditer aucun
> palier au feeling » : **on n'affiche un badge que s'il mesure un état VRAI**
> (référentiel câblé ou conformité réelle) — jamais un badge décoratif (ce
> serait le « badge pour le badge »
> qu'[ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)
> proscrit).
>
> Conformément à
> [ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md), **ce passage
> reste figé sur son _constat_** ; le tableau d'exécution ci-dessous est un
> **journal daté** de la réalisation (ce qui a été câblé, avec preuve et issue),
> pas une réécriture du diagnostic. La doctrine d'affichage est désormais tracée
> par [ADR 0080](../decisions/0080-notations-et-badges-readme.md).

### État d'exécution au 2026-06-16

Le câblage a été mené dans la foulée du passage ; la **rangée de badges groupée
par thématique** ([ADR 0080](../decisions/0080-notations-et-badges-readme.md))
est posée au README.

#### Lot 0 — badges honnêtes immédiats (faits ✅)

Référentiels **déjà câblés et nommés** : badge factuel stable, posés sans
attendre.

| Badge                    | État | Preuve                                              |
| ------------------------ | ---- | --------------------------------------------------- |
| **License: MIT**         | ✅   | `LICENSE` + `NOTICE` ; badge → fichier GitHub       |
| **Conventional Commits** | ✅   | commitlint hooks + CI ; `CHANGELOG.md` cite la spec |
| **SemVer**               | ✅   | release-please (`release-type: node`)               |
| **Keep a Changelog**     | ✅   | `CHANGELOG.md` au format ; badge → fichier GitHub   |
| **DOI** (préexistant)    | ✅   | DOI Zenodo concept + `CITATION.cff`                 |

#### Lot 1 — badges « notés » dynamiques (câblés ✅ / dépend d'une action externe ⏳)

| #   | Référentiel                      | État | Preuve / reste à faire                                                                                                                                                                        |
| --- | -------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **OpenSSF Best Practices Badge** | ⏳   | action **hors dépôt** : remplir bestpractices.dev (case #354). Badge posé une fois le projet créé.                                                                                            |
| 2   | **OpenSSF Scorecard**            | ✅   | `scorecard.yml` (actions SHA-pinnées) + `permissions: contents: read` sur `ci.yml` ; badge au README. Le **score** réel s'affiche après le 1ᵉʳ run sur `main`. Coche les cases axe 1 de #354. |
| 3   | **CI status**                    | ✅   | badge d'état `ci.yml/badge.svg` au README                                                                                                                                                     |

#### Lot 2 — mappings & audits (faits ✅ / écarté 🔶)

| #   | Référentiel     | État | Preuve / décision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| --- | --------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 4   | **FAIR**        | ✅   | mapping F-A-I-R→preuve dans [`bonnes-pratiques.md`](../architecture/bonnes-pratiques.md) (§ « référentiels externes »)                                                                                                                                                                                                                                                                                                                                                                           |
| 5   | **OpenGitOps**  | ✅   | mapping 4 principes→preuve dans `bonnes-pratiques.md`                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 6   | **WCAG / a11y** | 🔶   | **câblage différé — gain net insuffisant** ([ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md)) : `pa11y-ci` traîne un `puppeteer@9.1.1` (2021) qui **casse `pnpm docs:build`** (build script bloquant, ~136 paquets, Chromium ~300 Mo). Un **audit ponctuel** a tout de même tourné (Chrome système) et a trouvé un défaut réel (boutons `VPSwitch` sans nom accessible) → **issue #368**. À recâbler via `pa11y@8`/`@axe-core` (puppeteer récent) quand le besoin le justifie. |
| 7   | **REUSE/SPDX**  | 🔶   | **non adopté** : gain net jugé insuffisant (mono-licence) au critère 2 d'[ADR 0061](../decisions/0061-posture-adoption-bonnes-pratiques.md). Décision tracée, pas un manque.                                                                                                                                                                                                                                                                                                                     |

**Manques de fond promus en issues à part entière** (au-delà des badges — vraie
valeur communauté) : **signature des releases** (#366, check `Signed-Releases`
rouge), **SAST code** (#367, à évaluer vu l'IaC), **défaut a11y `VPSwitch`**
(#368, trouvé par l'audit ponctuel ; inclut le recâblage du job a11y sur un
outil à jour). Les cases « notations cyber » (Best Practices, CIS, NIST) restent
portées par **#354**.

**Non actionnables (constatés, pas des manques — donc pas de badge)** : DORA
(structurellement partiel, pas de prod), SRE error-budget (déjà tracé ADR 0062),
Green/SCI (horizon manifeste), ISO 27001/25010 (hors périmètre assumé), RGPD
(déjà issue gouvernance ADR 0041). Leur **absence de badge est un choix tracé**,
pas un oubli.

## Note de méthode et limites

- **Preuves vérifiées au 2026-06-16** : `CHANGELOG.md:3-8` (Keep a
  Changelog/SemVer/Conventional Commits cités) ; `CITATION.cff`
  (`cff-version 1.2.0`, DOI Zenodo) ; `README.md:52` (badge DOI) ;
  `release-config` (`release-type: node`) ; greps nuls re-confirmés :
  `bestpractices`/`WCAG`/`pa11y`/`SPDX-License-Identifier`/`OpenGitOps`/`DORA`/
  `ISO 27001`.
- **Badges non exécutés réellement** : les états « passing » du Best Practices
  Badge sont **prédits** depuis le code, pas issus d'un run du questionnaire
  officiel. Un remplissage réel peut nuancer.
- **FAIR/OpenGitOps non scorés** : ce passage constate l'**alignement de fait et
  l'absence de mapping**, pas une note formelle.
- **Frontière `cluster`/`atlas`** : seul `cluster` est audité. FAIR-**données**,
  data contracts et la qualification RGPD des datasets relèvent d'`atlas`
  (cadrés [ADR 0041](../decisions/0041-gouvernance-completude-dataops.md)).
- **Sœur de la note cyber** : les deux passages du 2026-06-16 se partagent
  l'angle « référentiels externes » — cyber d'un côté, tout le reste de l'autre
  — et **alimentent la même issue parapluie**.
- Ce passage est **figé**
  ([ADR 0058](../decisions/0058-doctrine-audit-grille-passages.md)) : il décrit
  l'état au **2026-06-16**.
