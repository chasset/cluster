# 0071 — NodePort : mécanisme d'exposition officiel au même titre que Gateway

## Statut

Proposed (2026-06-15)

Amende [ADR 0020](0020-exposition-reseau-tout-cilium.md) (lève l'écartement de
NodePort) ; complète [ADR 0048](0048-acces-local-developpeur.md) (accès hôte au
banc) et [ADR 0056](0056-modele-declaratif-topologies.md) §4 (`exposition` comme
dimension déclarative).

## Contexte

L'[ADR 0020](0020-exposition-reseau-tout-cilium.md) a retenu une exposition
**tout-Cilium** (LB-IPAM + L2 + Gateway API) et a **explicitement écarté
NodePort** : « _NodePort / `externalIPs` bruts. Ports hauts non stables, pas
d'IP stable, pas de routage host/path ni de terminaison TLS en bordure, et
contredit frontalement le principe #25 (services applicatifs non exposés).
Régression._ » (0020, section « Alternatives écartées »).

Trois faits, relus à l'usage, fragilisent cet écartement **absolu** :

1. **Le datapath NodePort est déjà armé, gratuitement.** `bootstrap/cni.sh:104`
   pose `--set kubeProxyReplacement=true`, et le commentaire au-dessus
   (`bootstrap/cni.sh:97-99`) note que ce flag « _active déjà
   NodePort/HostPort/ExternalIPs (flags `--enable-_` retirés en 1.19 → ne pas
   les poser)\* ». L'ADR 0020 elle-même l'écrit (0020 ligne 61-62). Autrement
   dit : **NodePort est servi en eBPF par Cilium dès aujourd'hui** ; il ne
   demande aucun composant, aucun flag, aucune CRD supplémentaire. Le coût
   marginal d'en faire un mode officiel est quasi nul.

2. **Gateway/LB-IPAM a un prérequis lourd que tous les terrains n'ont pas.**
   LB-IPAM exige une **plage d'IP réservée avec l'admin réseau** (0020 : « _IP
   prod non attribuée à l'aveugle … reste TODO explicite_ », et la même chose
   dans `platform/argocd/gateway.yaml` : « _plage IP prod du pool LB-IPAM … TODO
   admin réseau_ ») ; les annonces L2 sont en **beta** en 1.19 et exigent une
   **interface L2** annonçable sur le LAN (0020 §3) ; le Gateway exige des
   **CRDs Gateway API** (`test/lima/run-phases.sh:752-759`) et un **hostname +
   un certificat** cert-manager non vides (`platform/argocd/gateway.yaml:13`).
   Sur un terrain où l'IP virtuelle annonçable n'est pas négociable (lab, edge
   mono-NIC, cloud sans LB, démo jetable, CI), tout ce chemin est inopérant —
   alors que `NodeIP:30000-32767` marche immédiatement.

3. **Le champ `exposition.mode` existe déjà et annonce déjà `nodeport`.** Le
   modèle a le champ (`cluster_topology/model.py:48` et `:137`), le `socle`
   l'illustre avec ses trois valeurs (`topologies/socle.example.yaml`,
   commentaire `mode: lb-ipam # lb-ipam | nodeport | none`), idem
   `topologies/ha-3cp.example.yaml:52`. **Mais `nodeport` n'est aujourd'hui
   qu'une étiquette d'affichage** : la seule lecture du champ est
   `scripts/topology.py:888` (`exposition : {topo.exposition.get('mode', '—')}`)
   ; ni `cluster_topology/plan.py` ni `cluster_topology/layers.py` ne le
   consomment. La valeur `nodeport` est **annoncée mais non câblée** — un faux
   choix.

L'utilisateur demande que NodePort devienne un mécanisme d'exposition
**OFFICIEL**, déclarable **par topologie**
(`exposition.mode: nodeport | gateway`), **y compris hors banc**. Cela révise
frontalement le point « NodePort = régression » de l'ADR 0020. La question n'est
plus _Gateway OU NodePort pour tout le dépôt_ mais _quel mécanisme pour CETTE
topologie_ — exactement la logique catalogue de l'ADR 0023 (plusieurs infra
déclarées, une activée) et la dimension `exposition` posée par l'ADR 0056 §4.

## Décision

**NodePort devient un mécanisme d'exposition de premier rang, au même titre que
Gateway. Le choix se DÉCLARE par topologie via `exposition.mode`, et l'outil le
CÂBLE (il ne se contente plus de l'afficher).** Cinq points.

### 1. Deux mécanismes officiels, un critère de choix net

`exposition.mode` accepte trois valeurs (déjà annoncées dans les `.example`) :

- **`gateway`** (ex-`lb-ipam`, _cf._ point 3) — **bordure L7 complète** : IP
  virtuelle stable annoncée sur le LAN (LB-IPAM + L2), routage host/path
  (`HTTPRoute`), **terminaison TLS** par cert-manager (CA interne, ADR 0021),
  observabilité Hubble L7. **Le mode de référence pour un déploiement réel** où
  l'admin réseau fournit une plage d'IP et le DNS `*.cluster.lan` (ADR
  0020/0048).
- **`nodeport`** — **exposition L4 minimale, sans prérequis réseau** : un
  `Service type=NodePort` (port `30000-32767`) servi en eBPF par
  `kubeProxyReplacement` (déjà actif, `bootstrap/cni.sh:104`). Pas d'IP
  virtuelle à réserver, pas d'annonce L2, pas de CRD Gateway, pas de certificat
  de bordure obligatoire. Joignable sur **n'importe quelle IP de nœud**.
- **`none`** — aucune exposition câblée (services en ClusterIP seuls ; l'accès
  se fait par port-forward / `access.sh`, ADR 0048).

**Critère de choix (les deux sont légitimes, pas un défaut/exception) :**

| Besoin                                                                                         | Mode           |
| ---------------------------------------------------------------------------------------------- | -------------- |
| Routage host/path, terminaison TLS de bordure, IP stable annoncée sur le LAN, observabilité L7 | **`gateway`**  |
| Une plage LB-IPAM est négociée avec l'admin réseau **et** une interface L2 annonçable existe   | **`gateway`**  |
| Aucune IP virtuelle réservable (lab, edge mono-NIC, cloud sans LB, démo, CI)                   | **`nodeport`** |
| Exposition L4 brute suffisante (un port → un service), simplicité maximale                     | **`nodeport`** |
| Pas d'exposition hors cluster                                                                  | **`none`**     |

### 2. Le choix se déclare via `topology.yaml` → `exposition.mode`

C'est une **intention de déploiement**, déclarée dans la source de vérité unique
(ADR 0056). Le champ et son enum existent (`model.py:48/137`) ; cet ADR :

- **valide l'enum à la construction** (comme `VALID_LB_MODES` le fait pour le
  control-plane LB, `model.py:26` + `:153-159`) : un
  `VALID_EXPOSITION_MODES = {"gateway", "nodeport", "none"}` levant
  `TopologyError` sur valeur inconnue ;
- **rend le mode CONSÉQUENT** : `exposition.mode` pilote ce que `run-phases.sh`
  pose pour la bordure (point 5), au lieu d'être une simple étiquette
  (`topology.py:888`). « Déclarer, c'est obtenir » — un `nodeport` déclaré
  produit des `Service type=NodePort`, un `gateway` déclaré produit des
  `Gateway`+`HTTPRoute`.

`exposition` reste **orthogonal** à `layers` (ADR 0069) et au `backend`
(ADR 0036) : on peut combiner `layers: [gitops]` + `exposition.mode: nodeport`
aussi bien que `gateway`. Un nouvel `.example` pédagogique
(`topologies/nodeport.example.yaml`) illustre un palier
`exposition.mode: nodeport`, dans la lignée des `.example` non-préfixe de l'ADR
0069 (honnêteté : aucun `.example` existant n'est réécrit, ADR 0052/0069).

### 3. Renommage doux `lb-ipam` → `gateway`, rétrocompatible

L'enum historique nommait le mode bordure `lb-ipam` (l'implémentation), mais le
pendant de `nodeport` est conceptuellement **`gateway`** (le mécanisme, pas la
brique). On retient **`gateway`** comme nom canonique et on garde **`lb-ipam`
comme alias accepté** (mappé sur `gateway` à la lecture), pour ne pas casser les
`.example` existants (`socle.example.yaml`, `ha-3cp.example.yaml:52`) ni les
`topology.yaml` locaux gitignorés. Même patron « alias déprécié-doux » que
`catalog.profile` → `layers` (ADR 0069 §7).

### 4. Le port : range `30000-32767`, qui choisit

- **Plage** : l'intervalle standard Kubernetes `30000-32767`
  (`--service-node-port-range` par défaut), servi en eBPF par Cilium
  (`kubeProxyReplacement`).
- **Choix du port** : **auto par défaut** (l'apiserver alloue un port libre dans
  la plage) — c'est le comportement sûr (pas de collision, pas de valeur en dur
  à maintenir). Un port **fixe est OPT-IN**, déclaré par service quand la
  stabilité du port compte (URL mémorisable, règle pare-feu figée) :
  `exposition.nodeport.ports: { <id-endpoint>: 30080 }` dans `topology.yaml`,
  résolu vers le champ `spec.ports[].nodePort` du Service. **Aucun port fixe
  versionné comme défaut** (ADR 0023 : pas de valeur d'instance en dur) ; les
  ports fixes éventuels vivent dans la config locale gitignorée, l'`.example` ne
  montre que la forme.
- **Contrat** : `contract/endpoints.example.yaml` gagne, pour les endpoints
  exposables, un champ optionnel `nodeport` (auto / fixe) en regard du
  `ui_hostname` existant (qui reste le pendant Gateway) — un consommateur lit
  l'un OU l'autre selon le mode actif.

### 5. Cohérence Cilium : rien à armer, NodePort déjà en eBPF

`kubeProxyReplacement=true` (`bootstrap/cni.sh:104`) sert **déjà** ClusterIP,
NodePort, LoadBalancer en eBPF (`bootstrap/cni.sh:97-99` ; ADR 0020 ligne
61-62). Donc :

- **mode `nodeport`** : **zéro** flag/CRD/composant en plus. `run-phases.sh`
  pose des `Service type=NodePort` au lieu des `Gateway`/`HTTPRoute` ; le phase
  `platform-prereqs` (CRDs Gateway API, `run-phases.sh:752-759`) **n'est pas
  requis** pour ce mode (un terrain `nodeport` peut s'en passer).
- **mode `gateway`** : chemin ADR 0020 inchangé (LB-IPAM + L2 + Gateway API +
  cert-manager).
- **`externalTrafficPolicy`** : en mode `nodeport`, `Cluster` reste le défaut
  (cohérent ADR 0020 ligne 102-103 : `Local` droppe si le nœud ciblé n'héberge
  pas d'endpoint) ; `Local` est un opt-in si la préservation de l'IP source
  prime (au prix de devoir cibler un nœud porteur d'endpoint).

### 6. Défaut du banc Lima : `nodeport` (renversement assumé d'ADR 0020)

**Décision tranchée par l'auteur : le banc Lima passe en
`exposition.mode: nodeport` par DÉFAUT.** C'est le renversement le plus net de
l'ADR 0020 (qui faisait du Gateway/LB-IPAM le chemin de référence validé sur
banc), et il est **assumé explicitement** ici plutôt que laissé implicite :

- **Pourquoi** : NodePort (`NodeIP:30000-32767`, eBPF) marche sans plage IP
  réservée ni interface L2 annonçable — c'est le mode le plus reproductible sur
  un banc jetable (pas de négociation réseau, pas de prérequis cert/DNS de
  bordure). Pour « éprouver from-scratch » (ADR 0034), moins de prérequis
  externes = preuve plus robuste.
- **Ce que ça déplace** : la chaîne de preuve du mode `gateway` (LB-IPAM + L2 +
  Gateway API) ne passe plus par le DÉFAUT du banc. Elle reste prouvée par une
  topologie **`gateway.example.yaml`** dédiée (le banc Gateway devient un chemin
  explicite, pas l'implicite) — symétrique de ce que l'ADR proposait pour
  NodePort. `access.sh` (ADR 0048) reste compatible : il pose les Gateways
  uniquement quand le mode est `gateway` ; en `nodeport` il expose les
  `NodePort` (URLs `NodeIP:port`) sans forward SSH par Gateway.
- **Garde-fou honnêteté (ADR 0023/0052)** : le défaut `nodeport` du banc est un
  choix de **terrain `local`** ; il ne préjuge pas du défaut prod (un
  déploiement réel choisit `gateway` ou `nodeport` selon son réseau, point 1).
  Aucune valeur d'instance n'est figée — le port reste auto (point 4).

> **Conséquence forte** : l'ADR 0020 est amendé **au-delà** du seul drift
> `state.sh` — son invariant « validation Gateway obligatoire sur banc » est
> levé. La validation Gateway se fait désormais via `gateway.example.yaml`, pas
> via le défaut. Voir l'amendement ci-dessous.

### Amendement à l'ADR 0020 (drift `state.sh` — Couche 7b)

Le contrôle drift `bootstrap/state.sh:802-840` traite **tout**
`Service type=NodePort` comme un **DRIFT** (régression du principe #25),
n'excusant que `kubernetes-dashboard` (`:822`) et les Service de bordure Gateway
(`:817/:824-828`). C'est l'incarnation code de l'écartement 0020. Cet ADR
**l'amende** : quand `exposition.mode == nodeport`, les `Service type=NodePort`
**déclarés/posés par le chemin codé** deviennent une **exception tracée** (au
même titre que les Service LoadBalancer du Gateway le sont déjà), labellisés
pour être reconnus par l'allowlist (`exposition.cluster/managed-by=run-phases`
ou label équivalent). Le principe #25 reste : **exposition uniquement par un
mécanisme officiel déclaré** — Gateway **ou** NodePort — jamais un NodePort
manuel non tracé.

## Conséquences

**Bénéfices.**

- **Couverture de terrains élargie** : les topologies sans plage LB-IPAM
  négociable (lab, edge mono-NIC, cloud sans LB, CI, démo) ont enfin une
  exposition officielle et reproductible (ADR 0052), sans le prérequis réseau
  lourd du Gateway.
- **Coût marginal quasi nul** : le datapath NodePort est déjà armé
  (`cni.sh:104`) ; aucun composant ni flag ni CRD ajouté.
- **`exposition.mode` devient CONSÉQUENT** : le champ qui n'était qu'affiché
  (`topology.py:888`) pilote désormais la pose — fin du faux choix `nodeport`
  annoncé mais non câblé.
- **Deux mécanismes de premier rang** avec un critère explicite : plus de «
  NodePort = régression » par principe, mais un choix outillé par topologie (ADR
  0023/0056).

**Prix à payer.**

- **NodePort n'offre ni routage host/path ni TLS de bordure ni IP stable** —
  exactement ce que l'ADR 0020 lui reprochait. Ces limites restent **vraies** :
  c'est pourquoi `gateway` demeure le mode de référence d'un déploiement réel
  riche ; `nodeport` est le mode L4 minimal, pas un remplaçant universel.
- **Surface d'exposition plus large** : un port `30000-32767` ouvert sur chaque
  nœud. Acceptable sur réseau privé isolé (ADR 0003) ; à border par
  NetworkPolicy / pare-feu nœud si le terrain l'exige.
- **Deux chemins de pose à maintenir** dans `run-phases.sh` (Gateway vs
  NodePort) et deux formes dans le contrat (`ui_hostname` vs `nodeport`).
- **Ports fixes = risque de collision** s'ils sont mal choisis ; d'où le défaut
  **auto** et le fixe en opt-in local non versionné.

**Garde-fous.**

- **Enum validé à la construction** (`VALID_EXPOSITION_MODES`, `TopologyError`)
  — un mode inconnu échoue tôt, comme `VALID_LB_MODES` (`model.py:153-159`).
- **Aucun port fixe versionné** (ADR 0023) ; l'`.example` ne montre que la
  forme, les valeurs vivent en config locale gitignorée.
- **Drift tracé, pas relâché** : `state.sh` n'excuse que les NodePort **posés
  par le chemin codé** (label) en mode `nodeport` ; un NodePort manuel reste un
  drift (#25 préservé).
- **Preuve par run** (ADR 0034/0052) : un run from-scratch d'une topologie
  `exposition.mode: nodeport` (le service est joignable sur `NodeIP:<port>`) +
  rejeu `changed=0` — la justification empirique de la feature, comme pour tout
  nouveau câblage.

## À revoir si

- **Une plage LB-IPAM devient disponible partout** (admin réseau systématique) :
  `gateway` redeviendrait le seul mode pertinent et `nodeport` un repli de niche
  — sans le retirer (terrains CI/démo restent).
- **Le besoin d'IP stable + L4 sans L7** émerge (ex. un endpoint TCP non-HTTP
  exposé sur le LAN) : on ajouterait `exposition.mode: loadbalancer` (LB-IPAM
  sans Gateway), aujourd'hui couvert implicitement par `gateway`.
- **Le grain `exposition` doit descendre au service** (modes mixtes dans une
  même stack : UI en `gateway`, une API en `nodeport`) : `exposition` passerait
  d'un mode global à une table `par-endpoint`, sur le modèle du DAG par-couche
  de l'ADR 0069.

## Alternatives écartées

- **Garder NodePort écarté (statu quo ADR 0020).** Laisse les terrains sans
  LB-IPAM **sans exposition officielle reproductible**, et laisse `nodeport`
  annoncé dans les `.example` mais non câblé (`topology.py:888`) — un faux choix
  trompeur. Rejeté : on régularise une capacité déjà présente en eBPF.
- **NodePort réservé au banc uniquement** (comme les forwards SSH de l'ADR 0048
  sont banc-only). Rejeté : la demande est explicitement _hors banc_ ; le besoin
  (terrain sans plage IP) est réel en déploiement, pas un artefact de banc.
- **Réintroduire MetalLB pour les terrains sans Gateway.** Rejeté pour les mêmes
  raisons qu'en 0020 (composant externe, double annonce L2) : NodePort en eBPF
  couvre le besoin L4 minimal sans rien ajouter.
- **Ports fixes versionnés par défaut.** Rejeté : valeur d'instance en dur,
  contraire à l'ADR 0023, et source de collisions. Défaut **auto**, fixe en
  opt-in local.
- **Renommer `lb-ipam` sans alias.** Rejeté : casserait les `.example` et les
  `topology.yaml` locaux ; alias déprécié-doux retenu (parité ADR 0069 §7).
