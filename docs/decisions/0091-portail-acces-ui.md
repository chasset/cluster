# 0091 — Portail d'accès aux UI de la plateforme

## Statut

Proposed (2026-06-22) — mise en œuvre **incrémentale** suivie par
[`plan-portail.md`](../plans/plan-portail.md) (promotion Proposed→Accepted au
démarrage de l'implémentation).

Suite directe de l'[ADR 0048](0048-acces-local-developpeur.md) (accès local
développeur, aujourd'hui CLI banc-only) et de
l'[ADR 0043](0043-contrat-interface-cluster-atlas.md) (le contrat d'endpoints).
S'expose via l'[ADR 0071](0071-exposition-gateway-hostnetwork.md) (Gateway
hostNetwork) et respecte l'[ADR 0023](0023-plateforme-exemple-generique.md)
(valeurs génériques) et l'[ADR 0014](0014-durcissement-kubeadm-init.md)
(durcissement).

## Contexte

La plateforme expose une dizaine d'UI réparties par couche : `socle` (Kubernetes
Dashboard), `monitoring` (Grafana), `gitops` (Argo CD, Gitea), `dataops`
(Dagster, MLflow, mailpit…). Un opérateur n'a **aucune vue unifiée** de «
qu'est-ce qui est exposé, sous quel hostname, avec quelle authentification, et
comment récupérer le credential ».

1. **L'accès actuel est CLI et banc-only.** `bench/lima/access.sh`
   ([ADR 0048](0048-acces-local-developpeur.md)) génère un `.env` local jetable
   en lisant la **valeur** des Secrets (`secret_val`,
   `get secret … -o jsonpath={.data.<key>} | base64 -d`). C'est légitime là-bas
   (script hôte tournant avec le kubeconfig de l'opérateur), mais : (a) c'est du
   CLI, pas une vue navigable ; (b) les forwards SSH qu'il posait sont
   **désormais remplacés** par l'exposition hostPort 443
   ([ADR 0071](0071-exposition-gateway-hostnetwork.md)) ; (c) il ne couvre pas
   la prod.

2. **Le contrat liste déjà tout, mais n'est pas navigable.**
   `contract/endpoints.example.yaml` porte, par endpoint : `service`,
   `namespace`, `fqdn`, `layer`, `ui_hostname`, `auth` (∈ `none`, `token`,
   `secret-admin`, `secret-role`, `secret-obc`, `secret-static`).
   `contract/namespaces-secrets.example.yaml` porte, par catégorie d'auth, le
   **nom** du Secret + la **clé**. `scripts/check_contract.py` croise déjà ce
   contrat avec les **manifestes versionnés** — mais en statique, hors-ligne, et
   sans rien rendre pour un humain.

3. **Aucun croisement « le contrat dit » ↔ « l'API montre ».** Le contrat est le
   « DEVRAIT » (statique). L'état réel (`Service` présent, endpoints prêts,
   `Gateway`/`HTTPRoute` programmés, `Application` Argo CD `Synced/Healthy`) est
   le « EST » (live) et n'est lisible qu'à coups de `kubectl` épars.

**Fait décisif (contraintes navigateur vérifiées) :** les UI cibles posent
`X-Frame-Options`/`Content-Security-Policy: frame-ancestors` (Grafana, Argo CD,
Gitea) et des cookies de session `SameSite` — **embarquer ces UI en `iframe` est
techniquement bloqué** par le navigateur. Un portail ne peut donc être qu'un
**hub de liens**, pas un proxy d'affichage.

## Décision

> **Le portail est un petit serveur web _dynamique_ servi _dans_ Kubernetes, pas
> une page statique. Il lit l'API k8s en live et la croise avec le contrat ; il
> n'ouvre les UI qu'en lien nouvel onglet ; il n'affiche jamais la valeur d'un
> secret, seulement la commande pour l'obtenir.**

Cinq points.

### 1. Serveur dynamique in-cluster, dérivé du contrat ET de l'API live

Le portail est une **brique** `platform/portal/` (namespace + Deployment +
Service dédiés, modèle `platform/mailpit/`), servie par une **image maison**
(serveur HTTP Python in-cluster, modèle
`platform/dagster/image-openlineage/Dockerfile`). Au runtime, il lit :

- le **contrat** (le « DEVRAIT ») : `layer`, `auth`, `ui_hostname` attendu,
  nom/clé du Secret porteur du credential ;
- l'**API k8s** (le « EST ») : présence des `Service`, readiness via
  `EndpointSlice`, hostname réel et exposition via `Gateway`/`HTTPRoute`
  (`gateway.networking.k8s.io/v1`), état `sync`/`health` des `Application`
  (`argoproj.io/v1alpha1`).

La jointure se fait par la clé naturelle `(namespace, service)`, **exactement
comme `scripts/check_contract.py`** le fait déjà en statique (réutiliser ses
fonctions pures : `expected_fqdn`, résolution `backendRefs`, dérivation
d'opérateur CNPG/Rook). Le côté droit devient l'API live au lieu des manifestes.
**Conséquence cardinale : la vue est dérivée du contrat, donc jamais périmée** —
ajouter un endpoint au contrat l'ajoute au portail.

### 2. Rendu : sidebar par couche, liens en **nouvel onglet**, jamais d'iframe

La sidebar groupe les entrées par `layer` (`socle`, `monitoring`, `gitops`,
`dataops`). Chaque entrée est un **lien** (`target="_blank"`) vers le
`ui_hostname` réel. **Pas d'iframe** : `X-Frame-Options`/CSP `frame-ancestors`
et cookies `SameSite` des UI cibles l'interdisent (cf. fait décisif). Chaque
entrée affiche son verdict live — **MATCH** (contrat ∩ live cohérents),
**MISSING** (contrat dit présent, API ne trouve pas), **DRIFT** (hostname réel ≠
attendu, endpoints non prêts, ou Gateway non programmé), **EXTRA** (exposé en
bordure mais absent du contrat).

### 3. Secrets : afficher la **commande**, jamais la valeur — RBAC **sans** secrets

Pour une entrée dont `auth ≠ none`, le portail lit dans le contrat le **nom** du
Secret et la **clé**, puis affiche une **commande `kubectl` copiable** que
l'opérateur exécutera **avec ses propres droits**. Exemples (génériques,
[ADR 0023](0023-plateforme-exemple-generique.md)) :

```text
# auth: secret-admin (Argo CD)
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
# auth: secret-role (PostgreSQL/CNPG)
kubectl -n postgres get secret pg-role-<rôle> -o jsonpath='{.data.password}' | base64 -d
# auth: token (Kubernetes Dashboard, ADR 0010)
kubectl -n kubernetes-dashboard create token admin-user
# auth: secret-obc (bucket Rook/OBC)
kubectl -n <ns> get secret <obc> -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d
```

Le pod **n'exécute jamais** ces commandes ; il les **affiche**. Le credential
transite hôte ↔ apiserver de l'opérateur, **jamais par le pod portail**.

**Le RBAC du portail n'accorde AUCUN verb sur `secrets`.** En RBAC k8s, `get`/
`list` sur `secrets` renvoie l'objet complet (donc `.data`) : il n'existe
**pas** de droit « savoir qu'un Secret existe sans lire sa valeur ». Le seul
vrai least-privilege ([ADR 0014](0014-durcissement-kubeadm-init.md)) est donc
**zéro règle secrets** — même un bug du code portail ne peut alors lire un
Secret (le serveur API refuse, 403). Le `ClusterRole` se limite à `get`/`list`
sur les ressources **non sensibles** affichées : `services`, `endpointslices`
(`discovery.k8s.io`), `gateways`/`httproutes` (`gateway.networking.k8s.io`),
`applications` (`argoproj.io`). `ClusterRole` (lecture cross-namespace), sans
`watch` (le portail relit à la demande). Le SA `portal` est monté in-cluster —
modèle d'inspection, distinct du login humain du Dashboard
([ADR 0010](0010-dashboard-cluster-admin.md)).

### 4. Exposition : Gateway Cilium hostNetwork, hostname dédié

Le portail s'expose via le **Gateway hostNetwork**
([ADR 0071](0071-exposition-gateway-hostnetwork.md)) : `hostPort 443` sur l'IP
du nœud, hostname dédié `portail.cluster.lan` (placeholder `.lan`,
[ADR 0023](0023-plateforme-exemple-generique.md)), TLS de bordure cert-manager
([ADR 0021](0021-cert-manager-ca-interne.md)). Plus de forward SSH (la béquille
banc de l'[ADR 0048](0048-acces-local-developpeur.md) est remplacée par le
hostPort). Patron `Gateway` + `HTTPRoute` de `platform/mailpit/gateway.yaml`.

### 5. Durcissement

Pod durci ([ADR 0014](0014-durcissement-kubeadm-init.md)) : `runAsNonRoot`,
`seccompProfile: RuntimeDefault`, FS racine en lecture seule, aucune capability.
**NetworkPolicy** : egress vers l'**API server uniquement** (le portail ne parle
qu'à l'apiserver ; il n'atteint pas les UI lui-même — c'est le navigateur de
l'opérateur qui les ouvre). Image maison épinglée par digest
([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)), buildée comme
les autres images de la chaîne (`platform-build-images`, `build_all_arch`).

## Conséquences

**Positif :**

- **Vue unique** des UI installées (hostname, couche, auth, état live) pour un
  opérateur — fini les `kubectl` épars et le contrat illisible.
- **Dérivée du contrat** : ajouter un endpoint au contrat l'ajoute au portail,
  jamais de liste à maintenir en double (même esprit que `check_contract.py`).
- **Secrets jamais exposés** : le portail n'a pas le droit de lire un Secret ;
  il montre la commande. Sûr par construction (RBAC), pas par discipline.
- Le **croisement contrat ↔ API** signale les dérives (MISSING/DRIFT/EXTRA) — un
  outil de diagnostic d'exposition, pas qu'un annuaire.

**Coût / risques :**

- **Nouvelle brique** à déployer, durcir, exposer, et dont le RBAC est à auditer
  (`.trivyignore` éventuel justifié par chemin). Image maison à builder/pousser.
- Le portail **ne remplace pas** `access.sh` au banc (qui génère le `.env` atlas
  en lisant les valeurs — usage légitime côté hôte). Les deux coexistent :
  `access.sh` = outillage dev local ; portail = vue opérateur in-cluster.
- L'iframe étant exclu, le portail reste un **hub de liens** (pas un cockpit
  intégré). Accepté : c'est la seule option robuste vu les en-têtes des UI.

**Neutre :**

- Pas de page Astro/doc : le portail est **dynamique** (état live), incompatible
  avec une page statique générée au build
  ([ADR 0089](0089-doc-astro-starlight.md) reste le moteur de la _doc_, pas du
  portail).

## Voir aussi

- [Plan de mise en œuvre](../plans/plan-portail.md).
- [ADR 0048](0048-acces-local-developpeur.md) — accès dev local (CLI banc) que
  le portail complète côté opérateur in-cluster.
- [ADR 0043](0043-contrat-interface-cluster-atlas.md) — le contrat d'endpoints,
  source du portail.
- [ADR 0071](0071-exposition-gateway-hostnetwork.md) — exposition hostNetwork
  (hostPort 443) du portail.
- [ADR 0010](0010-dashboard-cluster-admin.md) — token Dashboard (modèle d'auth
  `token`, distinct du SA d'inspection in-cluster du portail).
