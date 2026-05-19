# StorageClasses

Définition des classes de stockage Ceph utilisables par les workloads du
cluster.

## Layout

| Dossier / fichier                                | Rôle                                                |
| ------------------------------------------------ | --------------------------------------------------- |
| [`block-replicated.yaml`](block-replicated.yaml) | Stockage bloc répliqué (RBD) — la classe par défaut |
| [`block-ec-retain.yaml`](block-ec-retain.yaml)   | Stockage bloc erasure-coded, `Retain`               |
| [`block-ec-delete.yaml`](block-ec-delete.yaml)   | Stockage bloc erasure-coded, `Delete`               |
| [`filesystem/`](filesystem/)                     | StorageClass CephFS (ReadWriteMany)                 |
| [`datalake/`](datalake/)                         | Object store S3-compatible (datalake)               |
| [`examples/`](examples/)                         | Exemples d'usage (PVC, services, etc.)              |
