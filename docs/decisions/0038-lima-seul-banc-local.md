# 0038 — Lima est le seul banc local ; le provisioning local n'est plus un axe

## Contexte

Le catalogue listait cinq axes de construction, dont **« provisioning local »**
avec plusieurs valeurs : Lima, Vagrant, VirtualBox (VM) et kind, k3d
(conteneurs). La réalité a divergé de cette liste :

- **kind est abandonné**
  ([ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)) : son image de
  node figeait Kubernetes en 1.31 (hors matrice, a cassé pgvector). Le spike
  Cluster Mesh a même été migré kind → Lima (#128).
- **k3d n'a jamais été retenu** : même reproche de fond que kind (k3s/conteneurs
  divergent du chemin `kubeadm` de prod) — jamais outillé dans le dépôt.
- **Vagrant / VirtualBox** ont servi au premier `multi-node-3` (validé
  28→31/05), mais **tout l'effort de fiabilisation récent** (bootstrap #127,
  DataOps #148 / #173, storageClass + S3 #158 / #186 — ~40 drifts catalogués)
  tourne **sur Lima**. Le harnais Vagrant n'est plus retesté et diverge ;
  VirtualBox n'a pas de support arm64 natif fiable (inexploitable sur Apple
  Silicon).

Conséquence logique : **en local, il ne reste qu'une seule valeur active —
Lima.** Or un axe à une seule valeur n'est pas un axe (rien à croiser). L'outil
de provisioning est par ailleurs déjà qualifié d'**attribut**, pas d'axe, par
l'[ADR 0030](0030-nomenclature-bancs-topologies.md).

## Décision

**Lima est le banc local de référence et unique. Le « provisioning » cesse
d'être un axe du catalogue : il devient un _attribut dérivé du terrain_.**

1. **Terrain → provisioner** (attribut, pas axe) :
   - terrain **local** → **Lima** (vrai `kubeadm` 1.34, même chemin que la prod)
     ;
   - terrain **cloud** → **OpenTofu**
     ([ADR 0032](0032-opentofu-provisioning-cloud.md)) ;
   - terrain **bare-metal** → manuel / PXE (non outillé à ce jour).
2. **Le catalogue passe de cinq à quatre axes** : matériel × topologie × terrain
   × briques. Le provisioner est une **colonne d'information**, déterminée par
   le terrain.
3. **Vagrant / VirtualBox : _deprecated_.** Conservés en l'état pour
   l'**historique des Runs** (`test/RESULTS.md`, banc Vagrant 28→31/05 — on ne
   réécrit pas le passé, [ADR 0023](0023-plateforme-exemple-generique.md)), mais
   **plus maintenus ni retestés**, et retirés des valeurs **actives** du
   catalogue. Le code (`test/multi-node/`, `test/single-node/` Vagrant) n'est
   pas supprimé maintenant — il porte la trace d'un build réel — mais n'évolue
   plus.
4. **kind / k3d : écartés** (rappel) — voies de provisioning conteneur non
   retenues (divergence de version / de chemin kubeadm).

## Statut

Accepted. (Complète [ADR 0006](0006-matrice-de-versions-et-politique-de-bump.md)
— abandon de kind — et [ADR 0030](0030-nomenclature-bancs-topologies.md) —
l'outil est un attribut. Restructure l'axe « provisioning » du catalogue.)

## Conséquences

- **Gain** : un seul harnais local à maintenir et fiabiliser (Lima). Le
  catalogue reflète la réalité (4 axes), sans axe dégénéré à une valeur. Moins
  d'ambiguïté pour un contributeur (« quel banc monter ? » → Lima).
- **Prix à payer** : plus d'alternative locale x86_64 via VirtualBox — mais elle
  n'était de toute façon pas exploitable sur Apple Silicon, et x86_64 relève
  désormais du **terrain cloud / bare-metal**
  ([ADR 0031](0031-terrain-cloud-arm.md)), pas de l'émulation locale.
- **Discipline** : ne pas faire évoluer le code Vagrant déprécié ; toute
  nouvelle validation locale passe par Lima. Si un terrain cloud/bare-metal est
  outillé, son provisioner s'ajoute comme attribut du terrain, pas comme nouvel
  axe.
- **Réversibilité** : si un besoin x86_64 local réapparaissait, rouvrir la
  question (Lima/QEMU ou autre) via un nouvel ADR — la dépréciation n'est pas
  une suppression.
