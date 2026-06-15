#!/usr/bin/env bash
#
# Accès développeur au banc Lima — UNE commande pour « git push et ça marche »
# (#232, ADR 0048). Le développeur data travaille dans le dépôt `atlas` ; il ne
# doit PAS opérer le cluster. Ce script rend le banc consommable depuis l'hôte :
#
#   1. pose les Gateways des UI dont le Service existe (dérivé du CONTRAT) ;
#   2. ouvre UN forward SSH par Gateway (chaque Gateway a SA propre IP LB), sur
#      un port hôte distinct (127.0.0.1:<port>), via la config SSH de Lima ;
#   3. pose un bloc /etc/hosts `*.cluster.lan → 127.0.0.1` (URLs cliquables) ;
#   4. récupère et regroupe les secrets/tokens (un seul écran) ;
#   5. génère `../atlas/.env.cluster.local` (gitignoré) consommable par atlas.
#
# POURQUOI SSH (et pas le portForward natif Lima ni des loopbacks 127.0.0.x) :
#   - le portForward natif Lima exige un REBOOT de la VM (pas de reload à chaud)
#     → casse temporairement le control-plane. Trop intrusif pour un accès.
#   - macOS ne bind pas 127.0.0.0/8 hors .1 sans `ifconfig alias` (sudo).
#   Le forward SSH dédié par Gateway est à chaud, sans sudo réseau, sans reboot.
#
# Source de vérité : contract/endpoints.example.yaml (ui_hostname/layer/auth) —
# rien n'est codé en dur (ADR 0023). Orchestration de CLIs → bash (ADR 0017) ;
# la LOGIQUE DE DÉCISION pure (bloc hosts, port par index, lignes .env) est
# isolée en fonctions testables (bench/unit/access.bats), sans cluster.
#
# Tout l'état (Gateways, /etc/hosts, forwards) est posé par du CODE reproductible
# — pas de `kubectl apply` manuel laissé en place (ADR 0046).
#
# Usage :
#   bench/lima/access.sh            # pose tout + affiche URLs/secrets + génère .env
#   bench/lima/access.sh --stop     # arrête les forwards, retire le bloc /etc/hosts
#   bench/lima/access.sh --print-hosts   # imprime le bloc /etc/hosts (pas de sudo)
#   bench/lima/access.sh --no-hosts      # tout sauf /etc/hosts (URLs en --resolve)
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=bench/lima/lib.sh
. "${HERE}/lib.sh" # log/ok/warn/die/need + REPO

CP="${CP:-cp1}"                       # control-plane (relais SSH des forwards)
KUBECONFIG_LOCAL="${KUBECONFIG_LOCAL:-${HERE}/.work/kubeconfig}"
KUBECTL=(kubectl --kubeconfig "${KUBECONFIG_LOCAL}")
CONTRACT="${CONTRACT:-${REPO}/contract/endpoints.example.yaml}"
ATLAS_DIR="${ATLAS_DIR:-${REPO}/../atlas}" # dépôt applicatif voisin (../atlas)
HOSTS_FILE="${HOSTS_FILE:-/etc/hosts}"
HOSTS_TAG="cluster.lan (banc Lima — bench/lima/access.sh)"
# Port hôte de base : la i-ème UI écoute sur BASE+i (8443, 8444, …). Non
# privilégié → aucun sudo pour les forwards (sudo seulement pour /etc/hosts).
BASE_PORT="${BASE_PORT:-8443}"
SSH_CFG="${HOME}/.lima/${CP}/ssh.config"

# ════════════════════════════════════════════════════════════════════════════
# Fonctions PURES (aucun kubectl / réseau / sudo) — testées en bats.
# ════════════════════════════════════════════════════════════════════════════

# host_port_for INDEX → port hôte de la i-ème UI (BASE_PORT + INDEX).
host_port_for() { printf '%s\n' "$((BASE_PORT + $1))"; }

# render_hosts_block HOSTNAME... → bloc /etc/hosts délimité, idempotent.
# Tous les hostnames pointent sur 127.0.0.1 (les forwards écoutent en local) ;
# c'est le PORT (un par UI) qui distingue le backend, pas l'IP.
render_hosts_block() {
    printf '# >>> %s >>>\n' "${HOSTS_TAG}"
    local h
    for h in "$@"; do
        printf '127.0.0.1\t%s\n' "${h}"
    done
    printf '# <<< %s <<<\n' "${HOSTS_TAG}"
}

# strip_hosts_block < fichier → contenu SANS le bloc délimité (retrait idempotent).
# Lit stdin, écrit stdout. Sûr si le bloc est absent (renvoie le fichier inchangé).
strip_hosts_block() {
    awk -v tag="${HOSTS_TAG}" '
        $0 == "# >>> " tag " >>>" { skip = 1; next }
        $0 == "# <<< " tag " <<<" { skip = 0; next }
        !skip { print }
    '
}

# env_line KEY VALUE → ligne `KEY=VALUE` pour le .env (valeur vide tolérée).
env_line() { printf '%s=%s\n' "$1" "${2:-}"; }

# read_lines VAR < flux → peuple le tableau nommé VAR (une entrée par ligne).
# Substitut portable de `mapfile`/`readarray`, absents du bash 3.2 de macOS
# (le banc tourne sur le poste de contrôle).
read_lines() {
    local __name=$1 __line
    eval "${__name}=()"
    while IFS= read -r __line; do
        eval "${__name}+=(\"\${__line}\")"
    done
}

# ════════════════════════════════════════════════════════════════════════════
# Lecture du contrat (yq) — quelles UI exposer (ui_hostname/namespace/service…).
# ════════════════════════════════════════════════════════════════════════════

# ui_hostnames → liste des ui_hostname déclarés dans le contrat (un par ligne).
ui_hostnames() {
    yq -r '.endpoints[] | select(.ui_hostname) | .ui_hostname' "${CONTRACT}"
}

# ui_rows → lignes `ui_hostname<TAB>namespace<TAB>service<TAB>layer<TAB>auth`,
# triées par hostname pour un ordre stable (port par index déterministe).
ui_rows() {
    yq -r '.endpoints[] | select(.ui_hostname)
        | [.ui_hostname, .namespace, .service, (.layer // "-"), (.auth // "none")]
        | @tsv' "${CONTRACT}" | sort
}

# ════════════════════════════════════════════════════════════════════════════
# Actions impures (kubectl, ssh, sudo) — orchestration.
# ════════════════════════════════════════════════════════════════════════════

svc_exists() { "${KUBECTL[@]}" -n "$1" get svc "$2" -o name > /dev/null 2>&1; }

# brique_for NS → dossier platform/<brique> du gateway.yaml. Convention du dépôt :
# <brique> = namespace, sauf grafana (chart kube-prometheus-stack).
brique_for() { [ "$1" = monitoring ] && echo kube-prometheus-stack || echo "$1"; }

# IP LoadBalancer du Gateway d'un namespace (Service cilium-gateway-<ns>). Vide si
# absent/pas encore programmé. `|| true` : sous `set -e`, un kubectl non-zéro
# (hoquet d'API juste après l'apply du Gateway) tuerait `lb_ip=$(gateway_lb_ip)`.
gateway_lb_ip() {
    local ns=$1
    # `-o jsonpath=<expr>` COLLÉ (un seul argument) : séparés, kubectl prend
    # l'expression pour un nom de service (« services {…} not found »).
    "${KUBECTL[@]}" -n "${ns}" get svc \
        -o 'jsonpath={range .items[?(@.spec.type=="LoadBalancer")]}{.status.loadBalancer.ingress[0].ip}{end}' \
        2> /dev/null || true
}

# Pose les Gateways des UI dont le Service existe (idempotent).
apply_gateways() {
    log "Pose des Gateways des UI présentes (dérivé du contrat)"
    local hostname ns svc layer auth brique gw
    while IFS=$'\t' read -r hostname ns svc layer auth; do
        svc_exists "${ns}" "${svc}" || { warn "${hostname} : service ${ns}/${svc} absent — Gateway non posé"; continue; }
        brique=$(brique_for "${ns}")
        gw="${REPO}/platform/${brique}/gateway.yaml"
        [ -f "${gw}" ] || { warn "${hostname} : ${gw#"${REPO}/"} absent — Gateway non posé"; continue; }
        "${KUBECTL[@]}" apply -f "${gw}" > /dev/null && ok "${hostname} : Gateway posé (${brique})"
    done < <(ui_rows)
}

# Ouvre un forward SSH dédié 127.0.0.1:<port> → <ip_lb>:443 (sans multiplexing :
# le ssh.config Lima a ControlMaster auto, qui empêcherait un canal persistant).
# IMPORTANT : `ssh -fN` se met en arrière-plan mais HÉRITE des descripteurs du
# script — si on ne ferme pas stdin/out/err, un `| tail` en aval reste bloqué
# (le pipe ne se ferme jamais). On détache donc explicitement les 3 flux.
open_forward() {
    local lport=$1 lb_ip=$2
    pkill -f "ssh.*-L 127.0.0.1:${lport}:" 2> /dev/null || true
    ssh -F "${SSH_CFG}" -o ControlMaster=no -o ControlPath=none -fN \
        -L "127.0.0.1:${lport}:${lb_ip}:443" "lima-${CP}" < /dev/null > /dev/null 2>&1
}

# Pour chaque UI : lit l'IP LB → ouvre un forward sur BASE_PORT+index. Mémorise
# le mapping hostname→port dans le tableau global UI_PORTS (pour l'affichage/.env).
#
# NB : on COLLECTE d'abord les lignes du contrat dans un tableau, PUIS on itère —
# au lieu de `while … < <(ui_rows)`. Raison : `ssh -fN` détaché hériterait du
# descripteur du process substitution et le maintiendrait ouvert → la boucle
# `read` ne verrait jamais EOF (script bloqué). Collecte préalable = pas de FD
# hérité par le ssh d'arrière-plan.
declare -a UI_PORTS=()
start_forwards() {
    [ -f "${SSH_CFG}" ] || die "config SSH Lima absente : ${SSH_CFG} (banc démarré ?)"
    log "Ouverture des forwards SSH (un par Gateway, port hôte dédié)"
    UI_PORTS=()
    local rows
    read_lines rows < <(ui_rows)
    local i=0 row hostname ns svc layer auth lb_ip lport tries
    for row in "${rows[@]}"; do
        IFS=$'\t' read -r hostname ns svc layer auth <<< "${row}"
        # L'IP LB peut tarder quelques secondes après l'apply du Gateway → retry.
        lb_ip=""; tries=0
        while [ -z "${lb_ip}" ] && [ "${tries}" -lt 10 ]; do
            lb_ip=$(gateway_lb_ip "${ns}")
            [ -n "${lb_ip}" ] && break
            tries=$((tries + 1))
            sleep 1
        done
        if [ -z "${lb_ip}" ]; then
            warn "${hostname} : pas d'IP LB (Gateway absent/non programmé) — ignoré"
            continue
        fi
        lport=$(host_port_for "${i}")
        if open_forward "${lport}" "${lb_ip}"; then
            ok "${hostname} → 127.0.0.1:${lport} (LB ${lb_ip})"
            UI_PORTS+=("${hostname}:${lport}")
        else
            warn "${hostname} : forward SSH échoué"
        fi
        i=$((i + 1))
    done
}

stop_forwards() {
    if pkill -f "ssh.*-L 127.0.0.1:.*:443" 2> /dev/null; then
        ok "forwards SSH arrêtés"
    else
        warn "aucun forward SSH actif"
    fi
}

# Pose le bloc /etc/hosts (sudo demandé EXPLICITEMENT). Idempotent.
apply_hosts() {
    local hostnames block tmp
    read_lines hostnames < <(ui_hostnames)
    block=$(render_hosts_block "${hostnames[@]}")
    log "Pose du bloc /etc/hosts (${#hostnames[@]} hostnames → 127.0.0.1) — sudo requis"
    tmp=$(mktemp)
    strip_hosts_block < "${HOSTS_FILE}" > "${tmp}"
    printf '%s\n' "${block}" >> "${tmp}"
    if sudo cp "${tmp}" "${HOSTS_FILE}"; then ok "/etc/hosts à jour"; else die "écriture /etc/hosts refusée (sudo ?)"; fi
    rm -f "${tmp}"
}

remove_hosts() {
    local tmp
    log "Retrait du bloc /etc/hosts — sudo requis"
    tmp=$(mktemp)
    strip_hosts_block < "${HOSTS_FILE}" > "${tmp}"
    if sudo cp "${tmp}" "${HOSTS_FILE}"; then ok "bloc /etc/hosts retiré"; else warn "retrait /etc/hosts refusé"; fi
    rm -f "${tmp}"
}

# Lit une clé d'un Secret (base64 → clair). Vide si le Secret/la clé manquent.
secret_val() {
    local ns=$1 name=$2 key=$3
    "${KUBECTL[@]}" -n "${ns}" get secret "${name}" -o jsonpath="{.data.${key}}" 2> /dev/null \
        | base64 -d 2> /dev/null || true
}

# port_of HOSTNAME → port hôte mappé (depuis UI_PORTS) ; vide si non forwardé.
# `return 0` final explicite : sans lui, une UI non forwardée (dashboard) ferait
# retourner le code du dernier test (1) → sous `set -e`, `port=$(port_of …)` tue
# le script. On veut « vide + succès », pas « échec ».
port_of() {
    local h=$1 e
    for e in "${UI_PORTS[@]}"; do
        [ "${e%%:*}" = "${h}" ] && { printf '%s\n' "${e##*:}"; return 0; }
    done
    return 0
}

# Affiche les URLs cliquables (port mappé par UI) + l'auth attendue.
print_urls() {
    log "UI accessibles (TLS CA interne — accepter le certificat la 1re fois)"
    local hostname ns svc layer auth port
    while IFS=$'\t' read -r hostname ns svc layer auth; do
        port=$(port_of "${hostname}")
        [ -n "${port}" ] || continue
        printf '    [%-10s] https://%s:%s   (auth: %s)\n' "${layer}" "${hostname}" "${port}" "${auth}"
    done < <(ui_rows)
}

# Affiche les secrets/tokens regroupés (un seul écran).
print_secrets() {
    log "Secrets & tokens (lus des Secrets du cluster — ne pas partager)"
    printf '    Argo CD   admin / %s\n' "$(secret_val argocd argocd-initial-admin-secret password)"
    printf '    Gitea     %s / %s\n' \
        "$(secret_val gitea gitea-admin username)" "$(secret_val gitea gitea-admin password)"
    printf '    Grafana   admin / %s\n' "$(secret_val monitoring kube-prometheus-stack-grafana admin-password)"
    local r
    for r in dagster pgvector marquez; do
        printf '    pg/%-8s %s / %s\n' "${r}" \
            "$(secret_val postgres "pg-role-${r}" username)" "$(secret_val postgres "pg-role-${r}" password)"
    done
}

# Génère ../atlas/.env.cluster.local (gitignoré) consommable par atlas.
generate_env() {
    [ -d "${ATLAS_DIR}" ] || { warn "dépôt atlas absent (${ATLAS_DIR}) — .env non généré"; return 0; }
    local out="${ATLAS_DIR}/.env.cluster.local"
    log "Génération de ${out#"${REPO}/../"} (gitignoré)"
    local pg_user pg_pwd gitea_user gitea_pwd
    pg_user=$(secret_val postgres pg-role-pgvector username)
    pg_pwd=$(secret_val postgres pg-role-pgvector password)
    gitea_user=$(secret_val gitea gitea-admin username)
    gitea_pwd=$(secret_val gitea gitea-admin password)
    {
        echo "# Généré par cluster/bench/lima/access.sh — NE PAS COMMITER (gitignoré)."
        echo "# Banc Lima local ; valeurs de déploiement (ADR 0023). Régénérer après un run."
        echo "# Postgres : FQDN intra-pod (le code atlas tourne dans le cluster) ou via"
        echo "# un kubectl port-forward dédié si exécuté depuis l'hôte."
        env_line POSTGRES_HOST "pg-rw.postgres.svc.cluster.local"
        env_line POSTGRES_PORT 5432
        env_line POSTGRES_DB pgvector
        env_line POSTGRES_USER "${pg_user}"
        env_line POSTGRES_PASSWORD "${pg_pwd}"
        env_line OPENLINEAGE_URL "http://marquez.marquez.svc.cluster.local:5000"
        env_line OPENLINEAGE_ENDPOINT "api/v1/lineage"
        env_line OPENLINEAGE_NAMESPACE dagster
        env_line REGISTRY "registry:80"
        env_line GITEA_PUSH_URL "http://${gitea_user}:${gitea_pwd}@127.0.0.1:3000/atlas/workflows.git"
    } > "${out}"
    ok "${out##*/} généré (PG, OpenLineage, registry, push Gitea)"
    warn "Vérifier qu'il est bien ignoré par git côté atlas (/.env.cluster.local)."
}

# ════════════════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════════════════
main() {
    local mode="${1:-up}"
    need yq
    need kubectl
    need ssh
    case "${mode}" in
        --stop)
            stop_forwards
            remove_hosts
            return 0
            ;;
        --print-hosts)
            local hostnames
            read_lines hostnames < <(ui_hostnames)
            render_hosts_block "${hostnames[@]}"
            return 0
            ;;
        up | --no-hosts) ;;
        *) die "usage : $0 [--stop|--print-hosts|--no-hosts]" ;;
    esac

    [ -f "${KUBECONFIG_LOCAL}" ] || die "kubeconfig absent (${KUBECONFIG_LOCAL}) — lancer 'run-phases.sh atlas'"
    require_lima
    apply_gateways
    start_forwards
    [ "${mode}" = --no-hosts ] || apply_hosts
    print_urls
    print_secrets
    generate_env
    log "Prêt. Travaillez dans ${ATLAS_DIR##*/} ; 'git push' (Gitea → Argo CD réconcilie)."
    [ "${mode}" = --no-hosts ] && warn "Sans /etc/hosts : ouvrez les URLs avec curl --resolve <host>:<port>:127.0.0.1."
    log "Pour tout arrêter : $0 --stop"
}

# Exécutable seul ou sourçable (tests bats des fonctions pures).
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
