# 0050 — Modèle de reprise / transactionnalité d'un rôle Ansible

## Contexte

La chaîne de bootstrap Ansible n'a **aucun mécanisme de reprise localisé**
(issue #236). Le seul `rescue:` existant (`platform-argocd`) est
**diagnostique** ; le seul rollback est
[`rollback.yaml`](../../bootstrap/rollback.yaml) — **global, destructif,
manuel**. Un échec en milieu d'étape stateful (CRI, `kubeadm init`/`join`)
laisse un **demi-état**, et la seule sortie documentée est souvent le rollback
destructif global → reprise lente.

Cet ADR fixe **comment un rôle reprend après défaillance**, en s'appuyant sur le
patron de rôle posé par l'[ADR 0049](0049-doctrine-choix-outil-par-action.md)
(il n'y a pas trois doctrines : 0049 dit _quel outil_, 0051 _comment écrire les
tâches_, 0050 _comment reprendre_).

## Décision

**Le `rescue:` dû à une étape dépend de sa nature, déclarative ou à effet de
bord.**

### Deux classes d'étape

- **(a) Étape déclarative-idempotente** (apply k8s, `copy`, `template`) — un
  re-run reprend la convergence. Le `rescue` **ne défait rien** : il
  **diagnostique** (capture l'état réel : pods/events via `k8s_info`) et `fail`
  avec un message actionnable. **Référence** : `platform-argocd` (rescue
  diagnostique). Supprimer Argo CD après un apply raté serait contre-productif.
- **(b) Étape à effet de bord non-idempotent** (`kubeadm init`/`join`, écriture
  config containerd + repos APT) — un re-run **nu** échouerait ou laisserait un
  demi-état. Le `rescue` doit **compenser** (`kubeadm reset --force`, retrait du
  demi-état du _seul_ step en cours) pour ramener à un point repris-able, **puis
  re-fail**.

### Trois invariants

1. **Tout step non-idempotent est gardé par un marqueur `creates:` (ou un
   pré-check explicite)** — c'est déjà le **checkpoint de-facto** : `admin.conf`
   (init), `node-joined.log` (join), `key1.b64` (clé enc), `lb-setup.log`. Un
   step déjà franchi ne re-rentre pas dans le `block`.
2. **La compensation locale rétablit l'idempotence du _step_**, elle ne fait
   **pas** le rollback global du nœud (cf. Frontière).
3. **Toute compensation réelle est banc-requise** : elle modifie le chemin
   d'erreur → se prouve par **arrêt injecté** (ADR 0034/0046).

### Frontière rescue local vs `rollback.yaml` global

|               | Rescue local (ce rôle)                                              | `rollback.yaml` / `k8s-rollback`                                         |
| ------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Portée        | le **step en cours**                                                | le **nœud entier**                                                       |
| Déclenchement | automatique (sur erreur du block)                                   | manuel (`-e confirm=yes`)                                                |
| Actions       | `kubeadm reset --force`, retrait des effets partiels de **ce** step | purge APT, `rm -rf /etc/kubernetes`, `modprobe -r`, rebuild from-scratch |

Règle : **le rescue local ne fait JAMAIS** purge APT / suppression massive
`/etc/kubernetes` / `modprobe -r` — c'est l'apanage de `k8s-rollback`. Si une
compensation de rescue duplique du code de `k8s-rollback`, factoriser un
`tasks/` partagé importable.

### Preuve par arrêts injectés — injection CÔTÉ HARNAIS

Les rescue compensateurs se prouvent par un harnais qui **injecte l'arrêt depuis
le banc** (kill du process `kubeadm` en plein step, **ou** suppression du
marqueur `creates:` entre deux runs), **jamais** par une variable `inject_fault`
lue par le rôle de production. Un rôle prod n'embarque aucun hook de test (ADR
0046 : le banc ne pollue pas le code prod). Le harnais : injecte → vérifie la
compensation (`kubeadm reset` passé, `/etc/kubernetes` propre) → relance le
**même** chemin → exige un run **vert**. Consigné dans `test/RESULTS.md`
(honnêteté des Runs).

## Statut

Accepted. Met en œuvre #236 ; s'appuie sur l'ADR 0049 (patron de rôle) et les
ADR 0034/0046 (preuve par run, injection côté harnais).

## Conséquences

- **Hors-banc** (cet ADR + cadrage) : la décision, la frontière, et la
  documentation en commentaire de tête des marqueurs-checkpoints existants.
  Correction de la **référence fausse** dans
  [`platform-argocd/tasks/main.yaml`](../../bootstrap/roles/platform-argocd/tasks/main.yaml)
  (le commentaire cite « ADR 0036 #236 » alors que 0036 = backing S3 ; le bon
  renvoi est **ADR 0050**).
- **Banc-requis** (suivis #236) : les rescue réparateurs sur `kubeadm init`,
  `kubeadm join`, et (si retenu) CRI ; le harnais d'arrêts injectés. Chacun à
  **re-prouver par un run**.
- **À trancher avant d'engager une fenêtre banc** : (1) le rescue **CRI** est-il
  utile (la `config.toml` est ré-écrite à chaque run → un simple re-run
  idempotent peut suffire, se rabattre alors sur le modèle diagnostique seul) ?
  (2) sur quel banc tournent les arrêts injectés (les scénarios 03/04 sont
  Vagrant ; Lima est le banc local de référence, ADR 0038) ?
