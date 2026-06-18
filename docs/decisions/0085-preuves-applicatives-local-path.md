# 0085 — Preuves applicatives sur local-path par défaut ; Ceph validé sur installation seule

## Statut

Proposed (2026-06-18)

## Contexte

La doctrine de banc distingue déjà deux profils
([ADR 0035](0035-strategie-bancs-fidelite-vitesse.md)) et plusieurs chemins
d'installation nommés ([ADR 0045](0045-chemins-installation-banc-couches.md)) :

- `atlas` — chaîne applicative complète (monitoring + GitOps + DataOps + MLflow)
  sur **local-path** + SeaweedFS (S3 léger), ~11 min ;
- `storage-real` — **stockage Ceph seul** (RBD via WordPress + smoke S3 RGW),
  sans chaîne applicative ;
- `cluster-dataops` / `atlas-ceph` — chaîne applicative **par-dessus Ceph**
  (RGW), ~30 min, plus haute fidélité.

**Constat opérationnel (2026-06-17/18).** Monter la chaîne applicative complète
**sur Ceph** (`atlas-ceph`/`cluster-dataops`) **ne tient pas en ressources** sur
le Mac de développement : un banc mono-nœud sature en CPU (`dagster-webserver`
Pending, `Insufficient cpu`, cf. [ADR sur `VM_CPUS`] / PR #412) et en disque
(DiskPressure, 125 pods Evicted, #391). Même un multi-nœud Ceph + chaîne MLOps +
MLflow + REDCap dépasse l'enveloppe mémoire/CPU/disque disponible. Résultat :
**de nombreuses issues de « preuve de banc » applicatives restaient bloquées**
derrière un montage Ceph irréalisable (#404 drift/CT, #414 REDCap, #407 logging
MLflow, #250 HA, #223 DataOps, #232 banc atlas).

**Le point qui débloque la décision**
([ADR 0036](0036-backing-s3-unique-rgw.md),
[ADR 0065](0065-variables-env-intention-vs-etat.md)) : le code applicatif
(CNPG + Barman, Loki, MLflow, registry) parle à S3 et au stockage par un
**chemin paramétré UNIQUE** — seul le _backing_ change (`seaweedfs` ↔ `rgw`) et
le _storageClass_ est **dérivé du cluster** (`detect_storage_profile`). Prouver
la chaîne applicative sur local-path exerce donc **le même code** que sur Ceph ;
ce ne sont pas deux chemins disjoints. La fidélité Ceph supplémentaire ne porte
que sur le **stockage** lui-même (RBD, résilience OSD, RGW réellement rempli),
pas sur le code applicatif.

## Décision

**Les preuves applicatives e2e se font désormais sur `local-path` par défaut.
Ceph n'est validé que sur son installation (montage du cluster + une
StorageClass + le smoke S3 RGW), pas avec la chaîne applicative montée
par-dessus.**

Concrètement :

1. **Preuve applicative = `atlas` (local-path), obligatoire.** Toute issue de «
   preuve de banc » portant sur l'**applicatif** (DataOps, MLflow, drift/CT,
   monitoring, GitOps, REDCap, HA…) se prouve sur `atlas`. C'est le défaut.
2. **Preuve Ceph = `storage-real` (installation seule), obligatoire.** Prouve
   que le cluster Ceph monte (OSD up, `HEALTH_OK`), qu'un PVC **RBD** bind
   (WordPress) et que le **RGW** répond (smoke S3 PUT/GET/DELETE). **Ne monte
   PAS** la chaîne applicative.
3. **Soupape RGW conservée — `cluster-dataops` devient « sur demande ».** La
   discipline de l'[ADR 0036](0036-backing-s3-unique-rgw.md) (« un changement S3
   validé en banc léger SeaweedFS doit être revalidé en banc Ceph RGW avant prod
   ») **reste en vigueur** : `cluster-dataops` (applicatif sur Ceph) n'est pas
   supprimé, mais passe de la cadence calendaire (90 j) à un **déclenchement par
   le risque** — joué **avant tout changement touchant le chemin S3/backing ou
   un storageClass**. C'est la SEULE preuve du « RGW rempli par un vrai workload
   » (backups CNPG/Barman → RGW, chunks Loki → RGW, artefacts MLflow → RGW) ; on
   ne la perd pas, on la déclenche quand elle compte.

Cette décision **amende
l'[ADR 0045](0045-chemins-installation-banc-couches.md)** : sa matrice de
couverture (§6) passe `cluster-dataops` de « optionnel 90 j » à « sur demande
(risque S3/stockage) », et acte que la preuve applicative de référence est
`atlas`, pas `atlas-ceph`.

## Conséquences

- **~6 issues de preuve applicative se débloquent** : elles se requalifient en
  preuve `atlas` (local-path), réalisable sur le Mac (#404, #407, #414, #250,
  #223, #232).
- **Aucune perte de couverture du code applicatif** : le chemin S3/storage est
  paramétré (ADR 0036/0065), donc local-path exerce le même code que Ceph.
- **Ceph reste prouvé** sur ce qui lui est propre : montage, RBD, RGW,
  résilience (scénarios 01–09, 19–22 via `storage-real`). On ne cesse PAS de
  tester Ceph — on cesse d'**empiler l'applicatif dessus** au banc.
- **Risque résiduel nommé** : une incompatibilité propre à l'**API RGW vs
  SeaweedFS** (signatures S3, multipart…) ne serait pas attrapée par la preuve
  local-path. La soupape `cluster-dataops` (point 3) la couvre, déclenchée par
  le risque.
- **Honnêteté des runs** ([ADR 0052](0052-reproductibilite-des-resultats.md)) :
  une preuve consignée doit dire **sur quel profil** elle a tourné. Une preuve
  `atlas` n'affirme rien sur le RGW rempli.

## À revoir si

- Le banc de développement gagne en ressources (ou bascule sur une machine
  dédiée / CI avec des nœuds plus gros) : on pourrait re-rendre `atlas-ceph`
  obligatoire.
- Une régression « passe en local-path, casse sur RGW » survient en prod : signe
  que la cadence de la soupape `cluster-dataops` est trop lâche → la re-rendre
  calendaire.
- Le code applicatif cesse d'être paramétré sur le backing (deux chemins S3
  disjoints réapparaissent) : la prémisse de cette décision tombe.

## Alternatives écartées

- **Garder l'applicatif sur Ceph obligatoire (statu quo `atlas-ceph` 7 j/30
  j).** Écarté : irréalisable en ressources sur le Mac → les preuves ne se
  faisaient simplement **pas** (issues bloquées). Une preuve non jouable n'est
  pas une preuve.
- **Supprimer purement `cluster-dataops`/`atlas-ceph`.** Écarté : on perdrait la
  seule preuve du « RGW rempli par un workload » et la soupape de revalidation
  S3 (ADR 0036). On le garde, sur demande.
- **Ne rien formaliser, juste re-tagger les issues.** Écarté : changement de
  politique de test structurant → un ADR le trace durablement (sinon on se
  redemandera dans 3 mois pourquoi `atlas-ceph` n'est plus joué). Convention du
  dépôt : décisions structurantes via ADR, pas en bullets de TODO.
