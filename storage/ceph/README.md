# Rook-Ceph

Stockage distribué pour le cluster basé sur [Rook](https://rook.io/) (opérateur
Kubernetes) et [Ceph](https://ceph.io/). Fournit du stockage bloc (RBD),
filesystem (CephFS) et objet (RGW compatible S3).

## Contenu

| Fichier                                                                                           | Rôle                                                  |
| ------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| [`crds.yaml`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/crds.yaml)           | Custom Resource Definitions de Rook                   |
| [`common.yaml`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/common.yaml)       | RBAC, namespace et ressources communes                |
| [`operator.yaml`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/operator.yaml)   | Déploiement de l'opérateur Rook                       |
| [`cluster.yaml`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/cluster.yaml)     | Définition du cluster Ceph                            |
| [`toolbox.yaml`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/toolbox.yaml)     | Pod toolbox pour exécuter des commandes `ceph`        |
| [`dashboard.yaml`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/dashboard.yaml) | Exposition du dashboard Ceph                          |
| [`cleanup.sh`](https://github.com/univ-lehavre/cluster/blob/main/storage/ceph/cleanup.sh)         | Effacement physique des disques après désinstallation |
| [`storageClass/`](/cluster/storage/ceph/storageClass/)                                            | StorageClasses (bloc, filesystem, objet)              |
| [`wordpress/`](/cluster/storage/ceph/wordpress/)                                                  | Exemple d'usage : MySQL + WordPress sur volume bloc   |

## Procédures

Voir [`RUNBOOK.md`](/cluster/storage/ceph/RUNBOOK/).
