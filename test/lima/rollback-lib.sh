#!/usr/bin/env bash
#
# Primitives du ROLLBACK PAR PHASE du banc (ADR 0054, issue #274). Défait UNE
# phase montée par run-phases.sh : efface namespaces + CRD + PVC + état node-side,
# force les finalizers récalcitrants (banc JETABLE → destructif total, pas de
# ménagement des données). Sourcé par test/lima/run-phases.sh (dispatch
# `rollback <phase>`). Distinct du rollback transactionnel #236 (rescue auto).
#
# Deux familles ici :
#  - FONCTIONS PURES (table de périmètre, ordre des dépendances, verdict d'état
#    propre) : NI kubectl NI ssh, prennent des valeurs déjà collectées, renvoient
#    un verdict `STATUS|message` ou une valeur. Testées par test/unit/rollback.bats
#    (comme state-classify.sh / bootstrap-fault-assert.sh).
#  - PRIMITIVES kubectl/ssh (k8s_force_delete_ns…) : font le réseau, NON pures.
#    Elles attendent les fonctions log/ok/die/vm_sh/KUBECTL de lib.sh/run-phases.sh.
#
# Convention verdict : une ligne "STATUS|message" (STATUS ∈ {ok, fail, skip}),
# découpée sur le premier '|'.

# ─── PARTIE PURE (testable bats, aucun réseau) ──────────────────────────────

# rollback_phase_namespaces PHASE
#   Namespaces qu'un rollback de PHASE doit effacer (séparés par des espaces),
#   ou vide si la phase n'a pas de namespace dédié. Table de périmètre (ADR 0054
#   §3), valeurs génériques banc (ADR 0023).
rollback_phase_namespaces() {
    case "${1:-}" in
        ceph | datalake) printf 'rook-ceph\n' ;;
        monitoring)      printf 'monitoring\n' ;;
        dataops)         printf 'postgres dagster marquez\n' ;;
        gitops)          printf 'argocd gitea\n' ;;
        *)               printf '\n' ;;  # sc, metrics-server, gitops-seed : pas de ns dédié
    esac
}

# rollback_phase_crd_groups PHASE
#   Groupes API dont les CRD doivent être supprimés (séparés par des espaces).
#   Supprimer un groupe CRD GC les CR restants. Vide si la phase n'installe pas
#   de CRD propres.
rollback_phase_crd_groups() {
    case "${1:-}" in
        ceph | sc | datalake) printf 'ceph.rook.io\n' ;;
        monitoring)           printf 'monitoring.coreos.com\n' ;;
        dataops)              printf 'postgresql.cnpg.io\n' ;;
        gitops)               printf 'argoproj.io\n' ;;
        *)                    printf '\n' ;;
    esac
}

# rollback_phase_has_nodeside PHASE
#   "yes" si la phase laisse un état NODE-SIDE que le delete Kubernetes ne couvre
#   pas (disques Ceph + /var/lib/rook). Seul `ceph` en a.
rollback_phase_has_nodeside() {
    case "${1:-}" in
        ceph) printf 'yes\n' ;;
        *)    printf 'no\n' ;;
    esac
}

# rollback_phase_downstream PHASE
#   Phases AVAL qui dépendent de PHASE (séparées par des espaces) : on ne défait
#   pas une phase socle tant qu'une de ses phases aval est encore montée
#   (ordre inverse, ADR 0054 §4). Vide si aucune.
rollback_phase_downstream() {
    case "${1:-}" in
        ceph)     printf 'sc datalake wordpress\n' ;;
        gitops)   printf 'gitops-seed\n' ;;
        *)        printf '\n' ;;
    esac
}

# rollback_known_phase PHASE
#   0 (vrai) si PHASE est une phase connue qui a un rollback défini. Sert au
#   dispatch à rejeter un nom inconnu.
rollback_known_phase() {
    case "${1:-}" in
        ceph | sc | datalake | metrics-server | monitoring | dataops | gitops | gitops-seed)
            return 0 ;;
        *) return 1 ;;
    esac
}

# classify_clean_state RESIDUAL
#   Verdict d'état propre après un rollback (ADR 0054 preuve). RESIDUAL = liste
#   (séparée par des espaces) des traces ENCORE présentes (ns/CRD/PVC/disque
#   sale) collectées par l'appelant ; vide = aucune trace.
#   - RESIDUAL vide → ok (rollback complet : zéro trace)
#   - sinon         → fail (liste les résidus → table de périmètre à compléter)
classify_clean_state() {
    local residual=${1:-}
    residual=${residual#"${residual%%[![:space:]]*}"}
    residual=${residual%"${residual##*[![:space:]]}"}
    if [ -z "$residual" ]; then
        printf 'ok|Rollback complet : aucune trace résiduelle\n'
    else
        printf 'fail|Traces résiduelles après rollback : %s (compléter la table de périmètre, ADR 0054 §3)\n' "$residual"
    fi
}

# classify_downstream_block PHASE PRESENT_DOWNSTREAM
#   Verdict du garde-fou d'ordre (ADR 0054 §4). PRESENT_DOWNSTREAM = liste des
#   phases aval ENCORE présentes (collectée par l'appelant).
#   - vide → ok (aucune phase aval → on peut défaire PHASE)
#   - sinon → fail (défaire PHASE laisserait les phases aval orphelines)
classify_downstream_block() {
    local phase=${1:-} present=${2:-}
    present=${present#"${present%%[![:space:]]*}"}
    present=${present%"${present##*[![:space:]]}"}
    if [ -z "$present" ]; then
        printf 'ok|Aucune phase aval présente — %s peut être défaite\n' "$phase"
    else
        printf 'fail|Phases AVAL encore montées (%s) : défaire %s d'\''abord (ordre inverse, ADR 0054 §4)\n' "$present" "$phase"
    fi
}
