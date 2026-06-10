# 0048 — Accès local développeur au banc (URLs cliquables + secrets + `.env`)

## Contexte

Le développeur data travaille dans le dépôt applicatif `atlas` ; son objectif
est de **se concentrer sur la data**, pas d'opérer le cluster. Or atteindre le
banc Lima depuis l'hôte demandait, jusqu'ici, des gestes d'opérateur : lancer un
`kubectl port-forward` par UI, lire chaque secret en `base64 -d`, savoir que le
service Grafana s'appelle `kube-prometheus-stack-grafana` ou qu'Argo CD sert en
HTTP clair (`server.insecure`). Charge cognitive « cluster » que le dev ne
devrait pas porter.

Trois contraintes propres au banc Lima local (toutes vérifiées) :

- le réseau de la VM (`user-v2`, ex. `192.168.104.0/24`) **n'est pas routable
  depuis l'hôte** macOS — c'est déjà pourquoi l'API K8s passe par un portForward
  `127.0.0.1:6443` (drift L5) ;
- les hostnames `*.cluster.lan` sont des **placeholders** qui ne résolvent pas
  côté hôte
  ([ADR 0021](0021-cert-manager-ca-interne.md)/[0020](0020-exposition-reseau-tout-cilium.md))
  ;
- **chaque Gateway Cilium a sa propre IP LoadBalancer** (une par namespace), pas
  une IP partagée.

Plusieurs voies « plus propres » ont été essayées et **écartées, preuves à
l'appui** :

- **portForward natif Lima** (`guestIP` non-localhost) : exige un **reboot de la
  VM** (pas de reload à chaud) ; le reboot casse temporairement le control-plane
  (apiserver indisponible le temps du redémarrage). Trop intrusif pour une
  simple commande d'accès.
- **IP loopback par UI** (`127.0.0.2`, `127.0.0.3`…) : macOS ne lie pas
  `127.0.0.0/8` hors `.1` sans `ifconfig alias` (sudo, non persistant).
- **`socket_vmnet`** (routage hôte→sous-réseaux VM) : exige sudo + une
  installation — précisément la dépendance que le banc a choisi d'éviter en
  retenant le réseau `user-v2`.

## Décision

**Un script unique — [`test/lima/access.sh`](../../test/lima/access.sh) — rend
le banc consommable depuis l'hôte en une commande, sans reboot, sans sudo
réseau, sans dépendance nouvelle. Le développeur ne fait que `git push` côté
`atlas`.**

Le script, en lisant le **contrat** comme source de vérité
([`contract/endpoints.example.yaml`](../../contract/endpoints.example.yaml), ADR
[0043](0043-contrat-interface-cluster-atlas.md)) :

1. **pose les Gateways** des UI dont le Service existe (idempotent), prérequis
   d'exposition déjà satisfaits par le chemin `atlas` (cert-manager + CRDs
   Gateway API) ;
2. **ouvre un forward SSH dédié par Gateway** —
   `127.0.0.1:<port> → <IP_LB_du_Gateway>:443` via la config SSH de Lima,
   multiplexing désactivé (`ControlMaster=no ControlPath=none`) pour un canal
   persistant. Un **port hôte distinct par UI** (8443, 8444…) ; c'est le port
   qui distingue le backend, pas l'IP (toutes en `127.0.0.1`) ;
3. **pose un bloc `/etc/hosts`** délimité `*.cluster.lan → 127.0.0.1` (sudo
   demandé explicitement ; `--print-hosts`/`--no-hosts` pour s'en passer) → URLs
   **cliquables**, TLS validé par la CA interne ;
4. **regroupe les secrets** (Argo CD, Gitea, Grafana, rôles Postgres) en un
   écran ;
5. **génère `../atlas/.env.cluster.local`** (gitignoré) — `.env` prêt à
   consommer côté `atlas` (Postgres, OpenLineage, registry, `GITEA_PUSH_URL`).
   Patron versionné générique : `contract/atlas.env.cluster.example` (ADR
   [0023](0023-plateforme-exemple-generique.md)).

Exposé aussi comme **phase** `test/lima/run-phases.sh access` (le chemin `atlas`
renvoie vers elle). Conforme à [ADR 0046](0046-corriger-le-code-pas-l-etat.md) :
l'état (Gateways, hosts, forwards) est posé par du **code reproductible**, pas
par des gestes manuels. La couche d'entrée reste **Gateway API Cilium**
inchangée (ADR 0020) — le sur-mesure est entièrement **côté hôte** et
**banc-only**.

## Statut

Accepted.

## Conséquences

- **Gain** : « git push et ça marche ». Le dev lance `run-phases.sh atlas` puis
  `access.sh`, obtient des URLs cliquables + un `.env` prêt, et travaille dans
  `atlas`. Plus de port-forward manuel, plus de `base64 -d`, plus de pièges de
  nommage de service.
- **Banc-only, assumé** : forwards SSH + `/etc/hosts` sont spécifiques au banc
  local. **En déploiement réel** (bare-metal), rien de tout ça : l'IP LB est sur
  le vrai LAN et l'admin réseau pose le DNS `*.cluster.lan` → les URLs Gateway
  marchent nativement.
- **Prix à payer** : ports hôte non standard (8443+), un process SSH par UI
  (tués par `--stop`), et un `sudo` ponctuel pour `/etc/hosts` (contournable).
  Acceptable pour un banc de dev.
- **Secrets en clair dans le `.env` généré** : c'est un fichier **local,
  gitignoré**, de valeurs de banc jetables (ADR 0023). Jamais commité (entrée
  `.env.cluster.local` ajoutée au `.gitignore` d'`atlas`).
- **Lien drift L57** : la commande `status` référençait `svc/grafana`
  (inexistant) ; corrigée vers `kube-prometheus-stack-grafana` au passage.
- **Pistes documentées comme écartées** (portForward natif, loopbacks,
  socket_vmnet) : si une version future de Lima recharge les portForwards à
  chaud, reconsidérer le natif (plus « intégré » que SSH).
