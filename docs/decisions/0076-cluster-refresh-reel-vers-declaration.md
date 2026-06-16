# 0076 — `cluster refresh` : matérialiser une évolution VOULUE du réel dans la déclaration

## Statut

Accepted (2026-06-16)

Calque `pulumi refresh` (rapatrier le réel), mais **borné par la doctrine
[ADR 0046](0046-corriger-le-code-pas-l-etat.md)** (le code est la source de
vérité). Étend `preview`/`classify_refresh` (qui CONSTATE déjà le drift) et
réutilise les sondes de
[`cluster discover`](0074-cluster-discover-reconstruire-topologie.md) (qui
RECONSTRUIT depuis zéro) ; frontière bash/Python de
l'[ADR 0049](0049-doctrine-choix-outil-par-action.md).

## Contexte

`topology.yaml` est la **source de vérité unique**
([ADR 0056](0056-modele-declaratif-topologies.md)) : on _déclare_, l'outil
_dérive et converge_. Deux directions existent déjà :

| Sens                       | Commande      | Ce qu'elle fait                                     |
| -------------------------- | ------------- | --------------------------------------------------- |
| déclaration → infra        | `up` / `next` | monte ce qui est déclaré (ADR 0056)                 |
| réel → déclaration (neuve) | `discover`    | RECONSTRUIT un `topology.yaml` de zéro (ADR 0074)   |
| réel ↔ déclaration (vue)   | `preview`     | CONSTATE le drift, sans l'écrire (classify_refresh) |

Il manque le **3ᵉ geste** : quand on fait évoluer le cluster **délibérément**
(ajouter un nœud, monter une couche de plus), `topology.yaml` reste **en
retard** sur cette intention réalisée. On doit aujourd'hui éditer le fichier **à
la main** pour le réaligner — fastidieux et source d'erreur. `discover` ne
convient pas : il **repart de zéro** (perd les commentaires, le `status`, les
choix non détectables comme `max_replicas`), il **ne fusionne pas** dans la topo
active.

### La tension à trancher (ADR 0046)

Rapatrier le réel dans la déclaration est **dangereux par construction** : c'est
exactement ce que `pulumi refresh` fait, et c'est aussi le geste que
l'[ADR 0046](0046-corriger-le-code-pas-l-etat.md) **proscrit** quand il s'agit
d'une **dérive** : « le code d'installation est la seule source de vérité ; tout
drift révélé → **corrigé dans le code**, pas entériné dans l'état ». Un
`refresh` naïf (réel→fichier en silence) **blanchirait une dérive accidentelle**
en la gravant dans la déclaration — l'inverse de la doctrine.

Le besoin est pourtant réel. La ligne de partage est l'**intention** :

- **Évolution VOULUE** (ajouter `node3`, monter `monitoring` en plus) : le réel
  est en AVANCE sur la déclaration, qu'on n'a pas encore mise à jour. La
  matérialiser dans `topology.yaml` est **correct** — c'est faire évoluer la
  déclaration, pas trahir le code.
- **Dérive ACCIDENTELLE** (un `kubectl patch` manuel, un composant posé hors
  modèle) : le réel CONTREDIT la déclaration. La rapatrier serait blanchir la
  dérive — **interdit** (ADR 0046 : corriger le code, re-prouver par un run).

L'outil ne peut pas LIRE l'intention. Donc il ne doit **jamais décider seul** :
il PROPOSE le diff, l'humain TRANCHE (comme `pulumi refresh --diff` + `up`).

## Décision

**Ajouter `cluster refresh` : il calcule le diff réel ↔ `topology.yaml` actif,
l'AFFICHE, demande CONFIRMATION, puis FUSIONNE le réel dans la déclaration
existante** (n'écrit jamais en silence, ne repart pas de zéro). Cinq points.

### 1. `refresh` PROPOSE, il n'IMPOSE pas (garde-fou ADR 0046)

`refresh` ne réécrit JAMAIS `topology.yaml` sans confirmation. Il imprime le
diff ligne à ligne (ce qui serait ajouté / changé), puis demande `[o/N]` (défaut
NON ; `--yes` pour la CI hors-TTY). C'est le **pendant déclaratif** du principe
« patch manuel = diagnostic seulement » (ADR 0046) : on regarde avant d'écrire.
Le `--diff`-only (`refresh --dry-run`) affiche sans rien modifier — équivalent à
`preview` ciblé sur la déclaration.

### 2. Ce que `refresh` rapatrie : les dimensions OBSERVABLES et DÉCLARATIVES

Uniquement ce qui est **à la fois** lisible du réel ET une dimension de
`topology.yaml` ([ADR 0056](0056-modele-declaratif-topologies.md) §4) :

- **nœuds & rôles** : un nœud Ready présent mais absent de la déclaration →
  proposé à l'ajout (`nodes[]`), rôle dérivé des labels (réutilise `discover`,
  ADR 0074) ;
- **couches montées** : une couche dont le signal d'infra est présent
  (`_LAYER_SIGNAL`) mais hors `layers:` → proposée à l'ajout ;
- **backend de stockage** : StorageClass réelle ≠ `storage.backend` déclaré →
  signalé.

**Hors périmètre — JAMAIS rapatrié** : le **scale** (replicas) — c'est une
capacité **runtime** dérivée du nombre de nœuds
([ADR 0072](0072-cluster-scale-replicas-noeuds.md)), **pas une dimension
déclarative**. Le nombre de replicas réel ne « met pas à jour » la topologie :
il n'y figure pas. De même, tout état applicatif interne (données, secrets) est
hors modèle.

### 3. SUPPRESSION proposée, jamais automatique

Un élément DÉCLARÉ mais ABSENT du réel (un nœud détruit, une couche défaite) est
le cas le plus ambigu : retrait volontaire, ou panne ? `refresh` le **signale**
(« déclaré mais absent ») et propose le retrait **séparément**, avec un défaut
encore plus prudent (jamais retiré sans `--prune` explicite). On n'efface pas
une intention déclarée sur la foi d'une absence (qui peut être une panne à
réparer, ADR 0046).

### 4. FUSION, pas réécriture — préserver la déclaration

`refresh` **édite** `topology.yaml` en place (ajoute/modifie les clés
concernées) au lieu de le régénérer. Il **préserve** : commentaires,
`catalog.status`, valeurs non détectables du réel (`max_replicas`, choix
d'exposition implicites), et l'ordre des clés. C'est la différence nette avec
`discover -o` (qui produit un fichier neuf, pour un cluster **non encore
déclaré**). Règle : `discover` = **adopter** un cluster sans topo ; `refresh` =
**réaligner** une topo existante.

### 5. Honnêteté : le drift entériné est TRACÉ

Tout `refresh` appliqué laisse une trace (le diff appliqué, horodaté), au même
titre qu'un drift corrigé dans le code est consigné (`registre-drifts.yaml`,
[ADR 0042](0042-fraicheur-preuves-banc.md)/0046). On distingue dans le registre
« drift corrigé dans le code » (le cas normal) de « évolution matérialisée par
refresh » (le cas de cet ADR) — pour qu'une revue voie _pourquoi_ la déclaration
a changé sans run de montage.

## Conséquences

- L'évolution délibérée d'un cluster (nœud/couche ajoutés) se **matérialise**
  dans `topology.yaml` sans édition manuelle ni perte de commentaires — puis
  `up`/`preview` repartent de la déclaration à jour.
- La doctrine ADR 0046 est **préservée** : `refresh` ne blanchit pas une dérive
  en silence (diff + confirmation + trace) ; une dérive accidentelle reste à
  corriger dans le code. Le scale (runtime, ADR 0072) n'est jamais rapatrié.
- Trois gestes réel↔déclaration cohérents : `preview` (constater), `discover`
  (adopter de zéro), `refresh` (réaligner l'existant).
- Façade fine (ADR 0049/0074 §6) : `refresh` réutilise les sondes de `discover`
  et la réconciliation de `preview` (`classify_refresh`), n'invente aucune
  détection.
- Preuve ([ADR 0034](0034-validation-e2e-from-scratch.md)/0052) : sur le banc,
  ajouter un nœud → `refresh` propose son ajout ; après confirmation,
  `topology.yaml` le déclare et `preview` ne montre plus de drift sur ce nœud.

## À revoir si

- `refresh` est utilisé pour blanchir des dérives à répétition (au lieu de
  corriger le code) → c'est un signal d'usage à contre-doctrine ; renforcer la
  trace (registre) ou restreindre les dimensions rapatriables.
- Le scale devient un jour DÉCLARATIF (replicas dans `topology.yaml`) → revoir
  le point 2 (le scale rejoindrait alors les dimensions rapatriables).
  Aujourd'hui il est runtime (ADR 0072), donc exclu.

## Alternatives écartées

- **Réécrire `topology.yaml` en silence (pulumi refresh nu)** : viole l'ADR 0046
  (blanchit une dérive). Rejeté — le diff + la confirmation sont non
  négociables.
- **Étendre `discover --merge` au lieu d'une commande dédiée** : `discover`
  reconstruit de zéro (perd commentaires/`status`/valeurs non détectables) ; le
  fusionner dans l'existant dénaturerait sa sémantique « adopter un cluster non
  déclaré ». Deux gestes distincts (adopter vs réaligner) = deux commandes
  claires.
- **Éditer `topology.yaml` à la main** (statu quo) : fastidieux, source
  d'erreur, pas de diff vérifié contre le réel. C'est ce que `refresh` remplace.
- **Rapatrier le scale** : le scale n'est pas déclaratif (ADR 0072) ; le mettre
  dans la topo changerait sa nature (runtime → déclaré) — autre décision.
