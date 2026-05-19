# cluster

[![DOI](https://zenodo.org/badge/1243564575.svg)](https://doi.org/10.5281/zenodo.20287209)

Manifests, playbooks et runbooks pour déployer et opérer un cluster Kubernetes
de recherche : installation, stockage distribué, applications de calcul et
services transverses.

## Structure

| Dossier                          | Rôle                                                               |
| -------------------------------- | ------------------------------------------------------------------ |
| [`bootstrap/`](bootstrap/)       | Installation initiale de Kubernetes (Ansible)                      |
| [`storage/ceph/`](storage/ceph/) | Stockage distribué (Rook-Ceph)                                     |
| [`platform/`](platform/)         | Services transverses (dashboard, registry, KubeVirt)               |
| [`apps/`](apps/)                 | Charges applicatives (Elasticsearch, Jupyter, RStudio, scratchpad) |

## Développement

Outillage géré par [Lefthook](https://lefthook.dev/) (hooks git),
[Prettier](https://prettier.io/) (format),
[yamllint](https://yamllint.readthedocs.io/),
[shellcheck](https://www.shellcheck.net/),
[kubeconform](https://github.com/yannh/kubeconform) et
[ansible-lint](https://ansible-lint.readthedocs.io/). Les messages de commit
suivent la convention
[Conventional Commits](https://www.conventionalcommits.org/).

### Installation

```bash
npm install                                          # installe lefthook + prettier + commitlint
brew install yamllint shellcheck kubeconform ansible-lint
```

`npm install` exécute automatiquement `lefthook install` qui pose les hooks git
(pre-commit, pre-push, commit-msg).

### Commandes utiles

```bash
npm run format         # applique Prettier
npm run lint           # vérifie format + yaml + shell
npm run lint:k8s       # valide les manifests via kubeconform
npm run lint:ansible   # lint les playbooks Ansible
npm run release        # bump version + met à jour CHANGELOG + crée tag git
npm run release:dry    # aperçu de la prochaine release sans rien modifier
```

## Trademarks

Tous les noms de produits et marques mentionnés dans ce dépôt sont la propriété
de leurs détenteurs respectifs.
