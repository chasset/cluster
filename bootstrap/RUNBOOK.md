# Runbook — Installation de Kubernetes

Procédure complète d'installation d'un cluster Kubernetes à partir de serveurs
Debian Bookworm, depuis la préparation OS jusqu'à la jonction des workers.

## Préparation des serveurs

### Préparation des disques pour le stockage distribué

Afin de préparer les disques pour le stockage distribué, lancez le script
suivant pour supprimer toutes les traces d’installation précédentes.

```bash
sudo rm -fR /var/lib/rook

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y gdisk parted

wipe_all() {
    device=$1
    echo "Device: ${device}"
    sudo sgdisk --zap-all ${device}
    if [ "${device}" == "/dev/nvme1n1" ]; then
        sudo blkdiscard ${device}
    else
        sudo dd if=/dev/zero of=${device} bs=1M count=100 oflag=direct,dsync
    fi
    sudo partprobe ${device}
}

for device in /dev/sd[a-z]
do
    wipe_all ${device}
done

wipe_all /dev/nvme1n1

sudo reboot
```

Vérifiez le nettoyage

```bash
lsblk
```

Afin d’obtenir

```bash
NAME                    MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda                       8:0    0   5,5T  0 disk
sdb                       8:16   0   5,5T  0 disk
sdc                       8:32   0   5,5T  0 disk
sdd                       8:48   0   5,5T  0 disk
sde                       8:64   0   5,5T  0 disk
sdf                       8:80   0   5,5T  0 disk
sdg                       8:96   0   5,5T  0 disk
sdh                       8:112  0   5,5T  0 disk
sdi                       8:128  0   5,5T  0 disk
sdj                       8:144  0   5,5T  0 disk
sdk                       8:160  0   5,5T  0 disk
sdl                       8:176  0   5,5T  0 disk
nvme0n1                 259:1    0 447,1G  0 disk
├─nvme0n1p1             259:2    0   512M  0 part /boot/efi
├─nvme0n1p2             259:3    0   488M  0 part /boot
└─nvme0n1p3             259:4    0 446,1G  0 part
  ├─control1--vg-root   254:0    0 445,1G  0 lvm  /
nvme1n1                 259:5    0   2,9T  0 disk
```

### Installation du système d’exploitation

Pour installer le système d’exploitation, utilisez l’image Debian Bookworm
(12.0) et suivez les instructions suivantes :

1. **Téléchargez l’image ISO** de Debian Bookworm (12.0) depuis le site
   officiel.
2. **Attachez l’image ISO** à la machine virtuelle ou au serveur physique.
3. **Démarrez l’installation** en sélectionnant l’image ISO comme périphérique
   de démarrage.

### Accès SSH par clef asymétrique

Une fois le système d’exploitation installé, il est recommandé de configurer
l’accès SSH par clef asymétrique pour une sécurité renforcée. Voici les étapes à
suivre :

Tout d’abord, connectez-vous au serveur via SSH en utilisant le mot de passe
initial.

```bash
ssh debian@control1
```

Une fois que la machine est enregistrée dans votre fichier `~/.ssh/known_hosts`,
vous pouvez configurer l’accès SSH par clef asymétrique. Déconnectez-vous.

Si vous n’avez pas de clef, générez-la et transférez-la :

```bash
ssh-keygen -t ed25519 -C "votre_email@example.com"
ssh-copy-id -i ~/.ssh/id_ed25519 control1
```

## Préparation du système d’exploitation des serveurs

Les opérations suivantes sont à réaliser sur tous les nœuds du cluster.

### Changer le mot de passe de l’utilisateur `debian`

```bash
passwd
```

### Autoriser l’utilisateur en sudo sans mot de passe

```bash
sudo visudo
```

Il est nécessaire d’ajouter la ligne : `debian ALL=(ALL) NOPASSWD: ALL`

### Sécurisation du protocole SSH

Modifier le fichier `/etc/ssh/sshd_config` :

```bash
PasswordAuthentication no
AllowUsers debian
PermitRootLogin no
PubkeyAuthentication yes
MaxAuthTries 3
Protocol 2
ClientAliveInterval 300
ClientAliveCountMax 3
```

Et relancer le service :

```bash
sudo systemctl restart sshd
```

### Désactiver le swap

Kubernetes refuse de s'installer si le swap est actif.

```bash
sudo lvdisplay
sudo umount /dev/control1-vg/swap_1
sudo lvremove /dev/control1-vg/swap_1
sudo lvdisplay
```

### Pare-feu

```bash
# Paramétrer le firewall
# Attention : ce paramétrage bloque l’accès au cluster IP
sudo apt-get update
sudo apt-get install ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
sudo ufw status verbose
```

## Installation de k8s

### CNI

Modifiez le fichier `hosts.yaml` pour y indiquer les adresses IP des machines du
cluster. Par exemple :

```yaml
cloud:
  children:
    control:
    workers:

control:
  hosts:
    control1:

workers:
  hosts:
    worker1:
    worker2:
```

Ensuite, exécutez les playbooks Ansible pour installer Kubernetes.

```bash
ansible-playbook -i ./hosts.yaml ./upgrade.yaml
ansible-playbook -i ./hosts.yaml ./checks.yaml
ansible-playbook -i ./hosts.yaml ./cri.yaml
ansible-playbook -i ./hosts.yaml ./kubeadm.yaml
ansible-playbook -i ./hosts.yaml ./control-planes.yaml
ansible-playbook -i ./hosts.yaml ./initialisation.yaml
```

Déplacez le fichier `cni.sh` sur le control plane (control1).

```bash
scp ./cni.sh control1:/home/debian
```

Exécutez le script sur le control node. Puis, une fois que les pods sont
disponibles, lancez la série de tests.

```bash
bash ./cni.sh
cilium connectivity test
```

### Join workers to cluster

```bash
ansible-playbook -i ./hosts.yaml ./join-workers.yaml
```

### Installation de la connexion en local

Récupérer le kubeconfig depuis le control plane :

```bash
mkdir -p ~/.kube
scp control1:/home/debian/.kube/config ~/.kube/config
```

Modifiez le fichier `~/.kube/config` pour y indiquer l’adresse IP du control
plane (control1). Ensuite, vous pouvez vérifier que tout fonctionne correctement
en exécutant les commandes suivantes :

```bash
k get nodes
k get pods --all-namespaces
```

### Virtual private network

Installer tailscale sur tous les nœuds.

```bash
curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt-get update
sudo apt-get install tailscale
sudo tailscale up --ssh
```

### Installation de Ceph

Voir [`storage/ceph/RUNBOOK.md`](../storage/ceph/RUNBOOK.md).

## Maintenance

### Mise à jour des systèmes d’exploitation

```bash
ansible-playbook -i ./hosts.yaml ./upgrade.yaml
```
