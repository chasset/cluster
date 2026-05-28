# Banc de test local (VirtualBox)

Canari **mono-nœud** pour valider les **phases 1-2** du bootstrap (préparation
OS, runtime containerd, `kubeadm init`, CNI Cilium) sur du **vrai Debian 12
arm64**, avant de toucher les serveurs.

## Réserves

- **Architecture** : arm64 (Apple Silicon), pas le x86_64 des serveurs HPE → on
  valide la **logique** (rôles, manifestes, câblage), pas les artefacts x86_64.
- **Échelle** : un seul nœud → pas de Ceph (qui exige ≥ 3 hôtes). On valide le
  bootstrap k8s + CNI, pas le stockage. Le multi-nœuds viendra ensuite.

## Pré-requis

VirtualBox, Vagrant, Ansible (+ la box `bento/debian-12` arm64, téléchargée
automatiquement).

## Utilisation

```bash
cd test

# 1. Démarrer la VM (crée aussi l'utilisateur `debian`)
vagrant up --provider=virtualbox

# 2. Générer l'inventaire (récupère le port SSH NAT attribué)
port=$(vagrant ssh-config | awk '/Port /{print $2}')
cat > inventory.yaml <<EOF
cloud:
  children:
    control:
    workers:
  vars:
    ansible_user: debian
    ansible_ssh_private_key_file: $HOME/.vagrant.d/insecure_private_keys/vagrant.key.ed25519
    ansible_ssh_common_args: -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
control:
  hosts:
    dirqual1:
      ansible_host: 127.0.0.1
      ansible_port: $port
workers:
  hosts: {}
EOF

# 3. Rejouer le bootstrap (phases 1-2)
for p in checks cri kubeadm control-planes initialisation; do
  ansible-playbook -i "$PWD/inventory.yaml" "../bootstrap/$p.yaml"
done

# 4. Installer le CNI
scp -P "$port" ../bootstrap/cni.sh debian@127.0.0.1:cni.sh
ssh -p "$port" debian@127.0.0.1 'bash cni.sh'

# 5. Vérifier
ssh -p "$port" debian@127.0.0.1 'kubectl get nodes; cilium status --wait'

# Réinitialiser
vagrant destroy -f
```

## Dernière validation (Debian 12 arm64)

`kubeadm`/`kubelet` **v1.34.8**, containerd.io **2.2.4** (`SystemdCgroup=true`,
CRI activé), Cilium **1.19.4** avec pod CIDR `10.244.0.0/16` (disjoint du réseau
nœuds), nœud `dirqual1` **Ready**.
