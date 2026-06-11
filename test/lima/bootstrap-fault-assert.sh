#!/usr/bin/env bash
#
# Fonctions PURES d'assertion pour le harnais d'ARRÊT INJECTÉ du bootstrap
# (#236 / rollback granulaire, ADR 0050). Prouvent que le `rescue:` d'un rôle à
# effet de bord NON idempotent (k8s-initialization, k8s-join-cluster) COMPENSE un
# `kubeadm init`/`join` avorté (`kubeadm reset --force`) puis permet un re-jeu
# vert du MÊME chemin nommé (ADR 0045/0050).
#
# Comme dataops-assert.sh / state-classify.sh : ces fonctions ne font NI ansible,
# NI ssh, NI réseau. Elles prennent une trace déjà collectée (codes de retour,
# sortie de playbook) et renvoient un verdict `STATUS|message` sur stdout
# (STATUS ∈ {ok, fail}). But : rendre la logique d'assertion du harnais testable
# SANS banc (test/unit/bootstrap-fault.bats).
#
# Convention : une ligne "STATUS|message", découpée sur le premier '|'. Aucune
# fonction n'appelle `exit` ni n'écrit ailleurs que sur stdout.

# parse_kubeadm_reset  (lit la sortie d'un playbook sur stdin)
#   Détecte si la COMPENSATION du rescue a été tracée : la tâche
#   « Compensate the aborted init/join (kubeadm reset --force) » s'exécute, OU la
#   signature `kubeadm reset` figure dans la sortie. PUR (grep sur stdin).
#   Émet "yes" si la compensation est tracée, "no" sinon.
parse_kubeadm_reset() {
    if grep -qiE 'kubeadm reset --force|Compensate the aborted (init|join)|\[Reset\]|cleaned up' ; then
        printf 'yes\n'
    else
        printf 'no\n'
    fi
}

# classify_compensation FIRST_RC RESET_SEEN SECOND_RC
#   Verdict du protocole d'arrêt injecté (ADR 0050). La preuve du rescue n'est
#   valable QUE si les TROIS conditions sont réunies, DANS CET ORDRE :
#     1. le 1er run ÉCHOUE  (FIRST_RC ≠ 0)         — la faute a bien pris,
#     2. la compensation est TRACÉE (RESET_SEEN=yes) — le rescue a joué,
#     3. le re-jeu RÉUSSIT  (SECOND_RC = 0)         — le chemin repart propre.
#   Tout écart invalide la preuve (ADR 0052 : un résultat non reproductible n'a
#   pas de valeur) :
#     - FIRST_RC=0            → la faute n'a PAS pris (rien à compenser) → fail,
#     - RESET_SEEN≠yes        → le 1er run a échoué SANS compensation → fail
#                               (demi-état laissé en place : rollback absent),
#     - SECOND_RC≠0           → la compensation n'a pas suffi à reprendre → fail.
#   PUR.
classify_compensation() {
    local first_rc=${1:-} reset_seen=${2:-} second_rc=${3:-}
    if [ "${first_rc}" = "0" ]; then
        printf 'fail|Faute non prise : le 1er run a RÉUSSI (rc=0) — rien à compenser, le rescue n'\''est pas exercé\n'
        return 0
    fi
    if [ "${reset_seen}" != "yes" ]; then
        printf 'fail|1er run échoué SANS compensation tracée (kubeadm reset absent) : demi-état laissé en place, rollback ADR 0050 absent\n'
        return 0
    fi
    if [ "${second_rc}" != "0" ]; then
        printf 'fail|Compensation insuffisante : le re-jeu a ÉCHOUÉ (rc=%s) — le chemin ne repart pas propre\n' "${second_rc}"
        return 0
    fi
    printf 'ok|Reprise prouvée (ADR 0050) : 1er run échoué → kubeadm reset compensé → re-jeu vert du même chemin\n'
}
