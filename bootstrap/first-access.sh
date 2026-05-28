#!/usr/bin/env bash
#
# Premier accès à des serveurs Debian 13 fraîchement installés.
#
# Sur chaque hôte fourni en argument, le script :
#   1. dépose la clé publique de l'opérateur (`ssh-copy-id`) ;
#   2. installe la règle sudo NOPASSWD pour `debian` ;
#   3. déploie un drop-in `sshd` durci (mot de passe off, root off, etc.) ;
#   4. active `unattended-upgrades` ;
#   5. (optionnel, via $NEW_DEBIAN_PASSWORD) change le mot de passe `debian`.
#
# Une fois ce script passé, les playbooks Ansible (et le dépôt
# `server-security`) peuvent piloter les nœuds sans mot de passe.
#
# Usage :
#   bootstrap/first-access.sh                  # cible dirqual1..dirqual4
#   bootstrap/first-access.sh dirqual1 dirqual2
#
# Variables d'environnement :
#   SSH_PUBKEY            clé publique à déposer  (défaut: ~/.ssh/id_ed25519.pub)
#   USER_REMOTE           utilisateur distant     (défaut: debian)
#   NEW_DEBIAN_PASSWORD   si défini, nouveau mot de passe `debian` (sinon, non touché)
#
# Le script demande deux fois le mot de passe par hôte la première passe
# (`ssh-copy-id` puis `sudo`). Les runs suivants sont silencieux.

set -euo pipefail

USER_REMOTE=${USER_REMOTE:-debian}
SSH_PUBKEY=${SSH_PUBKEY:-$HOME/.ssh/id_ed25519.pub}

hosts=("$@")
if [ ${#hosts[@]} -eq 0 ]; then
    hosts=(dirqual1 dirqual2 dirqual3 dirqual4)
fi

if [ ! -f "$SSH_PUBKEY" ]; then
    echo "ERREUR : clé publique introuvable : $SSH_PUBKEY" >&2
    echo "        Générer avec : ssh-keygen -t ed25519" >&2
    exit 1
fi

# Script joué côté nœud comme root via 'sudo bash -s'.
# Volontairement auto-contenu (heredoc simple-quoted, aucune expansion locale).
remote_harden() {
    cat <<'REMOTE'
set -euo pipefail

# 1) sudo NOPASSWD pour debian (drop-in, idempotent).
install -m 0440 /dev/stdin /etc/sudoers.d/90-debian-nopasswd <<'SUDOERS'
debian ALL=(ALL) NOPASSWD: ALL
SUDOERS

# 2) Durcissement SSHd via drop-in (prioritaire sur sshd_config principal).
install -m 0644 -D /dev/stdin /etc/ssh/sshd_config.d/00-hardening.conf <<'SSHD'
# Géré par cluster/bootstrap/first-access.sh — ne pas éditer à la main.
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
AllowUsers debian
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 3
SSHD
systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true

# 3) Mises à jour automatiques.
export DEBIAN_FRONTEND=noninteractive
apt-get -qq update
apt-get -qq -y install unattended-upgrades apt-listchanges
install -m 0644 /dev/stdin /etc/apt/apt.conf.d/20auto-upgrades <<'AUTO'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
AUTO
systemctl enable --now unattended-upgrades >/dev/null

echo "  → hardening appliqué"
REMOTE
}

for h in "${hosts[@]}"; do
    echo
    echo "== $h =="

    # (a) Dépôt de la clé publique. Demande le mot de passe debian la 1re fois.
    ssh-copy-id -i "$SSH_PUBKEY" "$USER_REMOTE@$h"

    # (b) Hardening en tant que root. sudo demande encore le mot de passe ici ;
    #     après cette passe, NOPASSWD est en place pour les fois suivantes.
    remote_harden | ssh -t "$USER_REMOTE@$h" "sudo bash -s"

    # (c) Optionnel : changement du mot de passe debian (passwordless via sudo).
    if [ -n "${NEW_DEBIAN_PASSWORD:-}" ]; then
        printf 'debian:%s\n' "$NEW_DEBIAN_PASSWORD" |
            ssh "$USER_REMOTE@$h" "sudo chpasswd"
        echo "  → mot de passe debian mis à jour"
    fi
done

echo
echo "Premier accès terminé sur : ${hosts[*]}"
echo "Ansible peut maintenant piloter ces nœuds sans mot de passe."
