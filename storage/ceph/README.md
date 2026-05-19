# Rook-Ceph

Stockage distribué pour le cluster basé sur [Rook](https://rook.io/) (opérateur
Kubernetes) et [Ceph](https://ceph.io/). Fournit du stockage bloc (RBD),
filesystem (CephFS) et objet (RGW compatible S3).

## Contenu

| Fichier                            | Rôle                                                  |
| ---------------------------------- | ----------------------------------------------------- |
| [`crds.yaml`](crds.yaml)           | Custom Resource Definitions de Rook                   |
| [`common.yaml`](common.yaml)       | RBAC, namespace et ressources communes                |
| [`operator.yaml`](operator.yaml)   | Déploiement de l'opérateur Rook                       |
| [`cluster.yaml`](cluster.yaml)     | Définition du cluster Ceph                            |
| [`toolbox.yaml`](toolbox.yaml)     | Pod toolbox pour exécuter des commandes `ceph`        |
| [`dashboard.yaml`](dashboard.yaml) | Exposition du dashboard Ceph                          |
| [`cleanup.sh`](cleanup.sh)         | Effacement physique des disques après désinstallation |
| [`storageClass/`](storageClass/)   | StorageClasses (bloc, filesystem, objet)              |
| [`wordpress/`](wordpress/)         | Exemple d'usage : MySQL + WordPress sur volume bloc   |

## Procédures

Voir [`RUNBOOK.md`](RUNBOOK.md).
