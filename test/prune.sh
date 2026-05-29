#!/usr/bin/env bash
# Détruit proprement les bancs Vagrant locaux (multi-node + single-node)
# et libère les disques VirtualBox associés.
#
# Idempotent : rejouer sur un banc déjà clean ne fait rien.
# Refuse de tourner si une VM dirqual* est `running` (--force pour passer
# outre, --help pour cette aide).
#
# Voir test/RESULTS.md drift 0c pour la justification du closemedium.

set -euo pipefail

FORCE=0
for arg in "$@"; do
    case "$arg" in
        -f | --force) FORCE=1 ;;
        -h | --help)
            awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
            exit 0
            ;;
        *)
            printf 'ERROR: option inconnue: %s\n' "$arg" >&2
            exit 2
            ;;
    esac
done

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

command -v vagrant > /dev/null || die "vagrant absent — brew install --cask hashicorp/tap/hashicorp-vagrant"
command -v VBoxManage > /dev/null || die "VBoxManage absent — brew install --cask virtualbox"

cd "$(dirname "$0")" || die "cd vers test/ échoué"
log "Cible : $(pwd)"

# Garde-fou : refuse de détruire des VMs en cours
running="$(VBoxManage list runningvms | grep -oE '"dirqual[0-9]+"' || true)"
if [[ -n $running && $FORCE -ne 1 ]]; then
    die "VM(s) en cours : ${running//$'\n'/ }. Arrête-les ou relance avec --force."
fi

for bench in multi-node single-node; do
    if [[ -d "${bench}/.vagrant" ]]; then
        log "vagrant destroy -f → ${bench}/"
        (cd "${bench}" && vagrant destroy -f 2>&1 | sed 's/^/    /')
    else
        log "${bench}/ : pas de .vagrant, skip"
    fi
done

# Drift 0c : vagrant destroy laisse parfois des disques VBox enregistrés
# (médiums) en plus des fichiers physiques. closemedium les unregister
# ET supprime le .vdi s'il existe encore.
orphans="$(VBoxManage list hdds \
    | awk '/^UUID:/{u=$2} /^Location:.*dirqual/{print u}')"
if [[ -n $orphans ]]; then
    log "Disques VBox orphelins (drift 0c) :"
    while read -r uuid; do
        [[ -z $uuid ]] && continue
        log "  closemedium ${uuid}"
        VBoxManage closemedium disk "$uuid" --delete 2>&1 | sed 's/^/    /' || true
    done <<< "$orphans"
fi

rm -rf .vagrant multi-node/.vagrant single-node/.vagrant
find . -maxdepth 3 -name '*VBoxHeadless*.log' -delete
log ".vagrant/ + logs VBoxHeadless supprimés"

remaining_vms="$(VBoxManage list vms | grep -cE '"dirqual[0-9]+"' || true)"
remaining_hdds="$(VBoxManage list hdds | grep -cE 'dirqual[0-9]+' || true)"
log "Reste VBox : ${remaining_vms} VM(s), ${remaining_hdds} disque(s) dirqual"
log "Banc propre."
