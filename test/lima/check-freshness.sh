#!/usr/bin/env bash
#
# Garde-fou de fraîcheur des preuves de banc — PAR CHEMIN (ADR 0042 §2 amendé,
# ADR 0045 §6 / #244).
#
# Chaque chemin nommé a SA cadence cible (ADR 0045 §6) : un run `atlas` frais ne
# doit PAS masquer un `storage-real` périmé. On lit donc, pour CHAQUE chemin
# surveillé, la date de son dernier run (champ `target` de runs-history.yaml,
# +hardening replié sur le chemin de base) et on la compare à SON seuil.
#
# Chemins surveillés :
#   - atlas         7 j   — OBLIGATOIRE (périmé → échec)
#   - storage-real  30 j  — OBLIGATOIRE (périmé → échec)
#   - cluster-dataops 90 j — WARN-ONLY (périmé → avertissement, n'échoue pas)
# Seuils surchargeables : SEUIL_ATLAS, SEUIL_STORAGE_REAL, SEUIL_CLUSTER_DATAOPS.
#
# La date vit DANS le contenu du YAML (le checkout CI ne préserve pas le mtime,
# ADR 0042 §3). Repli GLOBAL (ADR 0042 §4) : si l'historique est absent, on lit
# la date du log le plus récent sous runs/<date>-*.log et on applique SEUIL_JOURS.
#
# NON BLOQUANT côté PR : appelé uniquement par le cron
# (.github/workflows/bench-freshness.yml), jamais en pre-push.
#
# Usage :
#   test/lima/check-freshness.sh
#   SEUIL_STORAGE_REAL=45 test/lima/check-freshness.sh
#
# Codes de sortie : 0 = tous les chemins obligatoires frais ; 1 = au moins un
# périmé ; 2 = aucune preuve trouvée du tout.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# Fonctions PURES de metrology.sh (metro_age_days, metro_freshness_verdict,
# metro_last_date[_for_target], metro_seuil_for_target) — testées par bats.
LIMA_DIR="${HERE}"
# shellcheck source=test/lima/metrology.sh
. "${HERE}/metrology.sh"

SEUIL_JOURS="${SEUIL_JOURS:-7}"
HISTORY="${HERE}/runs-history.yaml"
RUNS_DIR="${HERE}/runs"

# Chemins obligatoires (un périmé → échec global) et optionnels (warn-only).
OBLIGATOIRES="atlas storage-real"
OPTIONNELS="cluster-dataops"

# Convertit une date ISO 8601 (UTC, ...Z) en epoch, portable macOS/Linux.
iso_to_epoch() {
    local iso=$1
    date -u -d "${iso}" +%s 2>/dev/null && return 0
    date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "${iso}" +%s 2>/dev/null && return 0
    return 1
}

now_epoch=$(date -u +%s)

# Évalue la fraîcheur d'UN chemin. Écrit une ligne de rapport sur stdout.
# Renvoie : 0 frais ; 1 périmé ; 3 aucun run pour ce chemin.
evaluer_chemin() {
    local target=$1 seuil iso past age verdict
    seuil=$(metro_seuil_for_target "${target}")
    iso=$(metro_last_date_for_target "${target}" < "${HISTORY}" || true)
    if [ -z "${iso}" ]; then
        echo "  • ${target} : aucun run consigné (seuil ${seuil} j)"
        return 3
    fi
    past=$(iso_to_epoch "${iso}" || true)
    if [ -z "${past}" ]; then
        echo "  • ${target} : date illisible ('${iso}')"
        return 3
    fi
    age=$(metro_age_days "${past}" "${now_epoch}")
    verdict=$(metro_freshness_verdict "${age}" "${seuil}")
    if [ "${verdict}" = frais ]; then
        echo "  ✓ ${target} : ${age} j ≤ ${seuil} j (${iso})"
        return 0
    fi
    echo "  ✗ ${target} : ${age} j > ${seuil} j — PÉRIMÉ (${iso})"
    return 1
}

# ── Cas sans historique : repli global sur le log le plus récent (ADR 0042 §4) ─
if [ ! -f "${HISTORY}" ] || [ -z "$(metro_last_date < "${HISTORY}" || true)" ]; then
    last_iso=""
    if [ -d "${RUNS_DIR}" ]; then
        latest_log=$(find "${RUNS_DIR}" -name '*.log' -type f 2>/dev/null | sort | tail -1)
        if [ -n "${latest_log}" ]; then
            last_iso=$(basename "${latest_log}" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}')
            [ -n "${last_iso}" ] && last_iso="${last_iso}T00:00:00Z"
        fi
    fi
    if [ -z "${last_iso}" ]; then
        echo "::warning::Aucune preuve de banc trouvée (ni runs-history.yaml ni runs/*.log)."
        echo "Aucun run consigné — lancer 'test/lima/run-phases.sh atlas' et committer la preuve."
        exit 2
    fi
    past=$(iso_to_epoch "${last_iso}" || true)
    [ -n "${past}" ] || { echo "::warning::Date illisible : '${last_iso}'."; exit 2; }
    age=$(metro_age_days "${past}" "${now_epoch}")
    verdict=$(metro_freshness_verdict "${age}" "${SEUIL_JOURS}")
    echo "Repli (pas d'historique) : dernier log ${last_iso} — ${age} j / seuil ${SEUIL_JOURS} j"
    [ "${verdict}" = frais ] && { echo "✓ Preuve de banc fraîche (repli log)."; exit 0; }
    echo "::warning::Preuve de banc périmée (repli, ${age} j > ${SEUIL_JOURS} j)."
    exit 1
fi

# ── Cas nominal : fraîcheur PAR CHEMIN ───────────────────────────────────────
echo "Fraîcheur des preuves de banc — par chemin (ADR 0045 §6) :"
fail=0
perimes=""

for t in ${OBLIGATOIRES}; do
    evaluer_chemin "${t}" || { fail=1; perimes="${perimes} ${t}"; }
done

# Optionnels : évalués et rapportés, mais n'échouent JAMAIS le verdict global.
for t in ${OPTIONNELS}; do
    rc=0
    evaluer_chemin "${t}" || rc=$?
    [ "${rc}" = 1 ] && echo "    (cluster-dataops périmé : avertissement seulement, non bloquant)"
done

if [ "${fail}" = 0 ]; then
    echo "✓ Chemins obligatoires frais."
    exit 0
fi

echo "::warning::Preuve de banc périmée pour :${perimes} — relancer ce(s) chemin(s) et committer le run."
exit 1
