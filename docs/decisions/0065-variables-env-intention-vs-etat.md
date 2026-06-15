# 0065 — Variables d'environnement : intention vs état détectable

## Statut

Accepted (2026-06-13)

## Contexte

Le harnais de banc (`bench/lima/run-phases.sh`, `rollback-lib.sh`, scénarios)
pilote son comportement par des **variables d'environnement**. En préparant la
commande `roundtrip` (détruire une couche → reconstruire → vérifier), une
question est apparue : **pourquoi la reconstruction d'une couche a-t-elle encore
besoin qu'on lui passe `WITH_CEPH=1` ?**

En creusant, ces variables se révèlent de **deux natures opposées**, aujourd'hui
indistinctes :

- certaines encodent un **état du déploiement** déjà présent et **constatable**
  — `WITH_CEPH` (le profil de stockage **est** dans le cluster : la StorageClass
  `rook-ceph-block-replicated` existe ou non), `WITH_HARDENING` (le durcissement
  **est** sur l'hôte : `sshd` durci, `auditd`/`fail2ban` actifs, constatés par
  [`bootstrap/state.sh`](../../bootstrap/state.sh)) ;
- d'autres encodent une **intention** de l'opérateur — un choix conscient ou un
  risque assumé qui **n'a pas de trace constatable** et **ne doit jamais être
  déduit** : `BANC_JETABLE` (« ce banc est jetable, détruis tout »), `BANC`
  (lever la garde offensive,
  [ADR 0025](0025-securite-active-chaos-attaques-controlees.md)), `SAFE`,
  `NO_CACHE`, `KEEP*`, `STRICT_*`, `TARGET`/`FAULT_TARGET`…

Passer un **état** en variable d'environnement est précisément le **drift L44**
([#319](https://github.com/univ-lehavre/cluster/issues/319)) : une phase
(`monitoring`/`dataops`/`gitops`) lancée **sans** `WITH_CEPH=1` sur un banc Ceph
choisit silencieusement le profil léger (`local-path`/SeaweedFS) → PVC
`Pending`. La valeur réelle aurait dû être **dérivée du cluster**, pas re-saisie
à la main. C'est aussi la doctrine « **corriger le code, pas l'état** » et « une
valeur de profil se **dérive** » de [CLAUDE.md](../../CLAUDE.md).

## Décision

**Une variable d'environnement encode soit une INTENTION, soit un ÉTAT
détectable — et le traitement diffère :**

| Nature                                          | Règle                                                                                                                |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Intention** (choix/risque assumé, sans trace) | **reste un flag EXPLICITE**. L'auto-détecter serait dangereux (on agirait sans ordre).                               |
| **État** du déploiement (constatable)           | **doit être AUTO-DÉTECTÉ** de la source réelle (cluster / hôte). Le coder en dur ou le re-saisir = drift (type L44). |

**Critère d'arbitrage** : « puis-je **constater** cette valeur sur le
déploiement existant, de façon fiable ? » Si oui → état, à détecter. Si non
(c'est une décision, un risque, une cible future) → intention, à garder
explicite.

### Conséquences actées

1. **`WITH_CEPH` (axe stockage) — auto-détecté IN-CLUSTER.** Les phases
   post-bootstrap (`monitoring`/`dataops`/`gitops`) dérivent leur
   `storageClass` + backing S3 de la **présence de la StorageClass Ceph**
   (`kubectl get sc rook-ceph-block-replicated`), au lieu de brancher sur
   `WITH_CEPH`. **Ferme
   [#319](https://github.com/univ-lehavre/cluster/issues/319) / drift L44.**

2. **`WITH_HARDENING` (axe durcissement) — auto-détecté VIA L'HÔTE (SSH).** Le
   durcissement est un état de l'hôte que `state.sh` constate déjà
   (`/etc/ssh/sshd_config.d/00-hardening.conf`, `auditd`/`fail2ban` actifs) ;
   cette détection devient réutilisable pour décider du profil de durcissement
   sans re-saisir `WITH_HARDENING`.

3. **Restent des flags EXPLICITES (intentions) :** `BANC_JETABLE`, `BANC`,
   `SAFE`, `NO_CACHE`, `KEEP*`, `STRICT_*`, `TARGET`/`FAULT_TARGET`,
   `SKIP_REBOOT`, `ALLOW_PENDING_OSD`, le dosage du chaos
   (`KILL_N`/`LOSS`/`DOWNTIME_S`). Les garde-fous destructifs (`BANC_JETABLE`)
   en particulier **doivent** rester un ordre conscient — les déduire annulerait
   leur raison d'être.

4. **`WITH_CEPH` au PROVISIONNING reste légitime.** À la phase `up` (attache des
   disques bruts, dimensionne la VM), **aucun cluster n'existe encore** : rien à
   détecter. `WITH_CEPH` y est un paramètre de provisionnement, pas un état — il
   est conservé. La règle ne vise que les phases **post-bootstrap** (contre un
   cluster vivant).

### Portée et garde-fous

- **Détection FIABLE ou refus franc.** Une auto-détection ambiguë (signal
  absent, cluster injoignable) ne doit pas deviner : elle échoue lisiblement,
  jamais ne suppose un profil par défaut silencieux (la leçon de L44).
- **Ne touche pas le socle Ceph du datalake**
  ([ADR 0018](0018-rook-ceph-vs-longhorn.md) /
  [0036](0036-backing-s3-unique-rgw.md)) : on dérive le profil, on ne change ni
  l'architecture de stockage ni le RGW.
- **Généralise aux futurs flags de profil.** Tout futur axe de stockage (p. ex.
  un éventuel 3ᵉ profil au catalogue) relève de la même règle : son profil se
  **détecte** du cluster, il ne s'encode pas en flag d'état. Cet ADR
  **n'implémente rien** d'un tel profil (gelé tant que sa propre ADR n'est pas
  Accepted, [ADR 0057](0057-gouvernance-documentaire-adr-plan-issue.md) §6) — il
  pose seulement le principe.
- **Re-preuve par run**
  ([ADR 0034](0034-validation-e2e-from-scratch.md)/[0052](0052-reproductibilite-des-resultats.md))
  : les changements de phases (axe stockage, puis durcissement) sont prouvés par
  un run de banc, pas par le lint seul (le drift L44 n'était visible que sur un
  run réel).

## Conséquences

Cet ADR fonde un **plan de mise en œuvre** (mise à jour ultérieure) et l'issue
[#319](https://github.com/univ-lehavre/cluster/issues/319) (axe stockage) ;
l'axe durcissement sera tracé par une issue dédiée. La commande `roundtrip` n'a
alors **aucun flag de profil à passer** : elle détruit puis reconstruit, et les
phases retrouvent seules le profil réel — réversibilité fidèle par construction.

### Alternatives écartées

- **Garder `WITH_CEPH` et le détecter côté outil** (le re-injecter dans
  l'environnement de `run-phases.sh`) : perpétue l'anti-pattern dans le harnais
  ; l'outil masquerait le drift au lieu de le supprimer à la source.
- **Tout auto-détecter, y compris les intentions** : dangereux — déduire
  `BANC_JETABLE` détruirait des données sans ordre conscient.
- **Tout garder explicite** : conserve le drift L44 (un état re-saisi à la main
  diverge tôt ou tard de la réalité).
