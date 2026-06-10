# 0051 — Options natives Ansible (idempotence, check_mode, server-side apply, handlers)

## Contexte

Une fois une brique en Ansible
([ADR 0049](0049-doctrine-choix-outil-par-action.md)), encore faut-il
**exploiter les directives natives** plutôt que de réimplémenter en
`command`/`shell`. L'idempotence est déjà largement couverte (77 `when:`, 37
`changed_when:`, 26 `retries:`), mais des écarts subsistent (issue #265),
vérifiés : `check_mode` **absent partout** (0 occurrence) ; des
`changed_when: true` constants (postfix) qui rapportent « changed » à tort et
**pilotent un handler de restart** ; `server_side_apply` à 5 endroits seulement
; un traitement de CRDs hétérogène (module vs `kubectl` shell).

Cet ADR fixe **comment écrire les tâches d'un rôle**, en s'appuyant sur le
patron de rôle posé par l'[ADR 0049](0049-doctrine-choix-outil-par-action.md)
(il ne le redéfinit pas).

## Décision

- **(a) `changed_when` reflète le _vrai_ changement** — jamais `true` constant
  sur une commande idempotente. Un `postconf -e` n'émet rien quand la valeur est
  inchangée → dériver `changed_when` du résultat réel (comparer via
  `postconf -h` enregistré, ou regex sur stdout). _Un `changed_when` qui pilote
  un handler de service (restart postfix) est un changement de comportement →
  **banc-requis**, prouvé par le scénario 22 (Mailpit)._
- **(b) `check_mode: false`** sur tout `command`/`shell` dont le **stdout
  enregistré pilote une logique aval**, pour rester compatible `--check`
  (dry-run). Ajout **purement additif** de l'attribut (sans toucher
  `changed_when`/ `when`) → vérifiable statiquement. Cibles :
  `containerd config default` (`k8s-CRI-install`), `kubeadm token create`
  (`k8s-pre-join`), `nerdctl manifest inspect` (`platform-build-images`),
  comptage disques (`ceph-pre-install`), `swapon --show` (`k8s-pre-install`).
- **(c) `server_side_apply`** (via le **module** `kubernetes.core.k8s`, avec
  `field_manager` dédié) pour les **CRDs et gros bundles**. Le
  `kubectl apply --server-side` en **shell** n'est toléré que sur
  **incompatibilité de parser documentée** (cas `platform-monitoring` : enum
  `- =` non quotées rejetées par PyYAML, acceptées par le parser Go de
  `kubectl`) — on ne le convertit pas.
- **(d) Pré-check qui skip** : un `command` à effet de bord est précédé d'un
  **pré-check idempotent** (modèle `platform-build-images` :
  `nerdctl manifest inspect` → bloc gardé par `when: img_present.rc != 0`)
  plutôt qu'exécuté inconditionnellement.
- **(e) Redémarrage de service TOUJOURS par handler** (`notify`), jamais
  `systemctl restart` inline. Constat : déjà respecté partout sauf le
  `daemon_reload` inline d'`etcd-backup` → à passer en handler notifié par les
  `copy` d'unités.

## Statut

Accepted. Met en œuvre #265 ; s'appuie sur l'ADR 0049 (patron de rôle) et l'ADR
0050 (reprise).

## Conséquences

- **Hors-banc** (diff additif / statiquement vérifiable, ansible-lint) :
  `check_mode: false` additif (d), `daemon_reload` → handler (e), et un job CI
  `ansible-playbook --syntax-check`/`--check` qui **donne du sens** aux
  annotations `check_mode` (sinon annotation morte non prouvée).
- **Banc-requis** (change l'écriture sur le cluster ou le déclenchement d'un
  handler) : `changed_when` postfix (a) → scénario 22 ; `server_side_apply`
  nouveaux (c) → managedFields ; pré-check CRD monitoring (d) → run. Suivis
  #265.
- **Garde-fou** : la cible reste « 0 tâche mutante non gardée hors du rollback
  dédié », sous le profil **production** d'ansible-lint (déjà en CI).
