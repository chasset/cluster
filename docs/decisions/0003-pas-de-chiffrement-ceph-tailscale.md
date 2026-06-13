# 0003 — Pas de chiffrement Ceph — sécurité du réseau déléguée

## Contexte

Ceph propose deux dimensions de chiffrement :

- **In-transit** : `network.connections.encryption.enabled` côté `CephCluster`
  (msgr2 messenger v2 avec secure mode).
- **At-rest** : chiffrement des OSDs via LUKS au niveau bluestore.

De même, le RGW (Rados Gateway, datalake S3) peut exposer TLS sur le port 443
plutôt que HTTP sur 80.

Le cluster :

- est confiné au **réseau privé `10.0.0.0/22`** (port 10 GbE inter-nœuds, pas de
  routage Internet) ;
- a un seul administrateur ; l'accès distant à l'API passe par
  `kubectl port-forward` depuis un poste autorisé à parler à l'API K8s ;
- héberge des données de recherche (article public, observation géoclimatique,
  etc.) — pas de données personnelles, pas de classifié.

Le chiffrement Ceph in-transit a un coût CPU non négligeable (chaque
réplication, chaque OSD↔OSD passé en chiffré). Le chiffrement at-rest LUKS
impose la gestion de clés (KMS, vault) et un overhead constant.

## Décision

**Aucun chiffrement Ceph n'est activé** :

- `network.connections.encryption.enabled: false` dans
  [`storage/ceph/cluster.yaml`](../../storage/ceph/cluster.yaml) ;
- pas de LUKS sur les OSDs ;
- RGW exposé en HTTP `port: 80` dans
  [`storage/ceph/storageClass/datalake/datalake-ec.yaml`](../../storage/ceph/storageClass/datalake/datalake-ec.yaml)
  ;
- pas de TLS sur le registry (cf. ADR 0011) ni sur le dashboard (port-forward
  kong-proxy local).

La sécurité du transport est **déléguée au contrôle d'accès au réseau** :

- intra-cluster : les flux restent confinés au `10.0.0.0/22` et au CIDR pods
  Cilium `10.244.0.0/16` ;
- accès distant : `kubectl port-forward` depuis un poste autorisé à parler à
  l'API K8s. Pour le trafic pod↔pod, Cilium chiffre déjà en WireGuard
  ([ADR 0019](0019-durcissement-reseau-cilium.md)) — couche réseau générique,
  indépendante de tout VPN d'accès.

## Statut

Accepted (2026-05-28). **Amendé (2026-06-13)** : abandon de Tailscale comme
tunnel d'accès distant (et de son repli Headscale) ; l'accès distant repose
désormais uniquement sur `kubectl port-forward`. Le titre/slug du fichier
conserve « tailscale » pour ne pas casser les liens entrants (identifiant ADR
stable) — la décision, elle, ne dépend plus de Tailscale.

## Conséquences

**Bénéfices.**

- Pas d'overhead CPU sur Ceph (réplications + lectures rapides).
- Pas de gestion de clés à inventer (pas de KMS, pas de Vault).
- Configuration plus simple à comprendre et à reprendre.

**Coûts assumés.**

- **Un attaquant qui passe sur le réseau cluster** (`10.0.0.0/22`) peut sniffer
  tout le trafic Ceph et les credentials S3. La sécurité périmétrique du réseau
  privé est le seul rempart.
- **Disques retirés du cluster** lisibles en clair (`ceph bluestore`). En cas de
  mise au rebut, faire un `blkdiscard` ou un wipe physique.

**À revoir si.**

- Le périmètre s'ouvre à des utilisateurs ou pairs non maîtrisés.
- Le cluster héberge des données réglementées (RGPD, données de santé,
  classifiées).
- Le réseau cluster cesse d'être isolé (point d'entrée externe direct).

**Si un accès distant durable devient nécessaire** (au-delà du `port-forward`
ponctuel), il sera tranché par un ADR dédié au moment voulu — sans présupposer
de solution (l'ancienne piste Tailscale/Headscale est abandonnée).

Cf. également [ADR 0011](0011-registry-http-sans-auth.md),
[ADR 0012](0012-rstudio-disable-auth.md) qui s'appuient sur la même hypothèse de
réseau de confiance.
