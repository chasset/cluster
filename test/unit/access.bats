#!/usr/bin/env bats
#
# Tests des fonctions PURES de test/lima/access.sh (accès dev, ADR 0048) :
# host_port_for, render_hosts_block, strip_hosts_block, env_line, read_lines.
# Aucun cluster, aucun réseau : on source le script (le garde BASH_SOURCE != $0
# empêche `main`) et on vérifie les sorties.

setup() {
    # shellcheck source=../../test/lima/access.sh
    source "${BATS_TEST_DIRNAME}/../../test/lima/access.sh"
}

@test "host_port_for : index 0 → BASE_PORT" {
    run host_port_for 0
    [ "$status" -eq 0 ]
    [ "$output" = "8443" ]
}

@test "host_port_for : index 4 → BASE_PORT+4" {
    run host_port_for 4
    [ "$output" = "8447" ]
}

@test "render_hosts_block : bloc délimité + une ligne 127.0.0.1 par hostname" {
    run render_hosts_block argocd.cluster.lan gitea.cluster.lan
    [ "$status" -eq 0 ]
    [[ "${lines[0]}" == "# >>> "* ]]
    [[ "${output}" == *$'127.0.0.1\targocd.cluster.lan'* ]]
    [[ "${output}" == *$'127.0.0.1\tgitea.cluster.lan'* ]]
    [[ "${lines[-1]}" == "# <<< "* ]]
}

@test "strip_hosts_block : retire le bloc, conserve le reste (idempotent)" {
    input=$(printf '1.2.3.4 garde\n%s\n5.6.7.8 garde2\n' "$(render_hosts_block argocd.cluster.lan)")
    run bash -c "printf '%s' \"\$1\" | { $(declare -f strip_hosts_block); HOSTS_TAG='${HOSTS_TAG}'; strip_hosts_block; }" _ "${input}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"1.2.3.4 garde"* ]]
    [[ "${output}" == *"5.6.7.8 garde2"* ]]
    [[ "${output}" != *"argocd.cluster.lan"* ]]
}

@test "strip_hosts_block : sans bloc, renvoie le fichier inchangé" {
    run bash -c "printf '%s\n' 'a' 'b' | { $(declare -f strip_hosts_block); HOSTS_TAG='${HOSTS_TAG}'; strip_hosts_block; }"
    [ "${lines[0]}" = "a" ]
    [ "${lines[1]}" = "b" ]
}

@test "env_line : KEY=VALUE" {
    run env_line FOO bar
    [ "$output" = "FOO=bar" ]
}

@test "env_line : valeur vide tolérée (KEY=)" {
    run env_line EMPTY ""
    [ "$output" = "EMPTY=" ]
}

@test "read_lines : peuple un tableau, une entrée par ligne" {
    read_lines arr < <(printf 'a\nb c\nd\n')
    [ "${#arr[@]}" -eq 3 ]
    [ "${arr[1]}" = "b c" ]
}
