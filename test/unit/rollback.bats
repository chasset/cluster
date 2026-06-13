#!/usr/bin/env bats
#
# Tests des fonctions PURES du rollback par phase (#274, ADR 0054). Aucun banc :
# on source la lib et on vérifie la table de périmètre + les verdicts sur des
# fixtures fixes (patron state-classify.bats / bootstrap-fault.bats).

setup() {
    # shellcheck source=../../test/lima/rollback-lib.sh
    source "${BATS_TEST_DIRNAME}/../../test/lima/rollback-lib.sh"
}

# ─── rollback_phase_namespaces ──────────────────────────────────────────────

@test "namespaces : ceph → rook-ceph" {
    run rollback_phase_namespaces ceph
    [ "$output" = "rook-ceph" ]
}

@test "namespaces : dataops → postgres dagster marquez" {
    run rollback_phase_namespaces dataops
    [ "$output" = "postgres dagster marquez" ]
}

@test "namespaces : gitops → argocd gitea" {
    run rollback_phase_namespaces gitops
    [ "$output" = "argocd gitea" ]
}

@test "namespaces : sc → vide (pas de ns dédié)" {
    run rollback_phase_namespaces sc
    [ -z "$output" ]
}

@test "namespaces : datalake → vide (PARTAGE rook-ceph, ne le supprime PAS)" {
    run rollback_phase_namespaces datalake
    [ -z "$output" ]
}

# ─── rollback_phase_targeted_resources (phases sans ns propre) ──────────────

@test "targeted : datalake → CephObjectStore + SC bucket (pas le ns rook-ceph)" {
    run rollback_phase_targeted_resources datalake
    [[ "$output" == *"cephobjectstore.ceph.rook.io datalake"* ]]
    [[ "$output" == *"rook-ceph-datalake"* ]]
    [[ "$output" != *"namespace"* ]]
}

@test "targeted : sc → StorageClasses bloc/fs ciblées" {
    run rollback_phase_targeted_resources sc
    [[ "$output" == *"rook-ceph-block-replicated"* ]]
}

@test "targeted : metrics-server → deploy kube-system" {
    run rollback_phase_targeted_resources metrics-server
    [[ "$output" == *"-n kube-system deployment.apps metrics-server"* ]]
}

@test "targeted : ceph → vide (ceph passe par ns + CRD, pas ciblé)" {
    run rollback_phase_targeted_resources ceph
    [ -z "$output" ]
}

@test "targeted : monitoring → OBC loki-buckets dans rook-ceph (libère datalake)" {
    # L'OBC du backing S3 de Loki vit dans rook-ceph (ns ≠ monitoring) : sans elle,
    # le CephObjectStore datalake reste bloqué en Deleting. #319-suite.
    run rollback_phase_targeted_resources monitoring
    [[ "$output" == *"-n rook-ceph objectbucketclaim.objectbucket.io loki-buckets"* ]]
}

@test "targeted : dataops → OBC cnpg-backups dans rook-ceph (libère datalake)" {
    run rollback_phase_targeted_resources dataops
    [[ "$output" == *"-n rook-ceph objectbucketclaim.objectbucket.io cnpg-backups"* ]]
}

# ─── rollback_phase_crd_groups ──────────────────────────────────────────────

@test "crd : ceph → ceph.rook.io" {
    run rollback_phase_crd_groups ceph
    [ "$output" = "ceph.rook.io" ]
}

@test "crd : dataops → postgresql.cnpg.io" {
    run rollback_phase_crd_groups dataops
    [ "$output" = "postgresql.cnpg.io" ]
}

@test "crd : metrics-server → vide" {
    run rollback_phase_crd_groups metrics-server
    [ -z "$output" ]
}

@test "crd : sc/datalake → vide (ne PAS supprimer les CRD ceph.rook.io partagés)" {
    run rollback_phase_crd_groups sc
    [ -z "$output" ]
    run rollback_phase_crd_groups datalake
    [ -z "$output" ]
}

# ─── rollback_phase_has_nodeside ────────────────────────────────────────────

@test "nodeside : ceph → yes (disques + /var/lib/rook)" {
    run rollback_phase_has_nodeside ceph
    [ "$output" = "yes" ]
}

@test "nodeside : monitoring → no" {
    run rollback_phase_has_nodeside monitoring
    [ "$output" = "no" ]
}

# ─── rollback_phase_downstream ──────────────────────────────────────────────

@test "downstream : ceph → sc datalake wordpress" {
    run rollback_phase_downstream ceph
    [ "$output" = "sc datalake wordpress" ]
}

@test "downstream : gitops → gitops-seed" {
    run rollback_phase_downstream gitops
    [ "$output" = "gitops-seed" ]
}

@test "downstream : monitoring → vide" {
    run rollback_phase_downstream monitoring
    [ -z "$output" ]
}

# ─── rollback_known_phase ───────────────────────────────────────────────────

@test "known : ceph → 0 (connue)" {
    run rollback_known_phase ceph
    [ "$status" -eq 0 ]
}

@test "known : up → 1 (pas de rollback de phase défini)" {
    run rollback_known_phase up
    [ "$status" -ne 0 ]
}

@test "known : nom inconnu → 1" {
    run rollback_known_phase n-importe-quoi
    [ "$status" -ne 0 ]
}

# ─── classify_clean_state ───────────────────────────────────────────────────

@test "clean_state : aucun résidu → ok" {
    run classify_clean_state ""
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "clean_state : espaces seuls → ok (normalisation)" {
    run classify_clean_state "   "
    [[ "$output" == ok\|* ]]
}

@test "clean_state : résidus → fail (les liste)" {
    run classify_clean_state "ns/rook-ceph crd/ceph.rook.io"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"rook-ceph"* ]]
}

# ─── classify_downstream_block ──────────────────────────────────────────────

@test "downstream_block : aucune aval → ok" {
    run classify_downstream_block ceph ""
    [ "$status" -eq 0 ]
    [[ "$output" == ok\|* ]]
}

@test "downstream_block : aval présente → fail (refuse l'ordre)" {
    run classify_downstream_block ceph "sc datalake"
    [[ "$output" == fail\|* ]]
    [[ "$output" == *"sc datalake"* ]]
    [[ "$output" == *"ordre inverse"* ]]
}
