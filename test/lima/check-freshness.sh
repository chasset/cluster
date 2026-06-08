#!/usr/bin/env bash
#
# Garde-fou de fraîcheur des preuves de banc (ADR 0042).
#
# Lit la date du DERNIER run consigné dans test/lima/runs-history.yaml et la
# compare au seuil (défaut 7 jours, ADR 0042 §2). Au-delà → sort en échec avec un
# message explicite. NON BLOQUANT côté PR : ce script n'est appelé QUE par le
# workflow cron (.github/workflows/bench-freshness.yml), jamais en pre-push.
#
# La date vit DANS le contenu du YAML (le checkout CI ne préserve pas le mtime,
# ADR 0042 §3). Repli (ADR 0042 §4) : si l'historique est absent, on lit la date
# du log le plus récent sous runs/<date>-*.log.
#
# Usage :
#   test/lima/check-freshness.sh            # seuil 7 j
#   SEUIL_JOURS=14 test/lima/check-freshness.sh
#
# Codes de sortie : 0 = frais ; 1 = périmé ; 2 = aucune preuve trouvée.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# On réutilise les fonctions PURES de metrology.sh (metro_age_days,
# metro_freshness_verdict, metro_last_date) — testées par bats, pas de
# duplication. lib.sh n'est pas requis (LIMA_DIR posé localement).
LIMA_DIR="${HERE}"
# shellcheck source=test/lima/metrology.sh
. "${HERE}/metrology.sh"

SEUIL_JOURS="${SEUIL_JOURS:-7}"
HISTORY="${HERE}/runs-history.yaml"
RUNS_DIR="${HERE}/runs"

# Convertit une date ISO 8601 (UTC, ...Z) en epoch, portable macOS/Linux.
iso_to_epoch() {
    local iso=$1
    # GNU date (Linux/CI) :
    date -u -d "${iso}" +%s 2>/dev/null && return 0
    # BSD date (macOS) :
    date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "${iso}" +%s 2>/dev/null && return 0
    return 1
}

# 1. Source de fraîcheur : la date de la dernière entrée de l'historique.
last_iso=""
source_desc=""
if [ -f "${HISTORY}" ]; then
    last_iso=$(metro_last_date < "${HISTORY}" || true)
    [ -n "${last_iso}" ] && source_desc="runs-history.yaml"
fi

# 2. Repli (ADR 0042 §4) : date en tête du nom du log le plus récent.
if [ -z "${last_iso}" ] && [ -d "${RUNS_DIR}" ]; then
    latest_log=$(find "${RUNS_DIR}" -name '*.log' -type f 2>/dev/null \
        | sort | tail -1)
    if [ -n "${latest_log}" ]; then
        # Nom de la forme AAAA-MM-JJ-*.log → on prend la date, minuit UTC.
        last_iso=$(basename "${latest_log}" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}')
        [ -n "${last_iso}" ] && last_iso="${last_iso}T00:00:00Z"
        [ -n "${last_iso}" ] && source_desc="runs/$(basename "${latest_log}")"
    fi
fi

if [ -z "${last_iso}" ]; then
    echo "::warning::Aucune preuve de banc trouvée (ni runs-history.yaml ni runs/*.log)."
    echo "Aucun run consigné — lancer 'test/lima/run-phases.sh all' et committer la preuve."
    exit 2
fi

# 3. Calcul de l'âge et verdict (fonctions pures).
now_epoch=$(date -u +%s)
past_epoch=$(iso_to_epoch "${last_iso}" || true)
if [ -z "${past_epoch}" ]; then
    echo "::warning::Date illisible dans ${source_desc} : '${last_iso}'."
    exit 2
fi

age=$(metro_age_days "${past_epoch}" "${now_epoch}")
verdict=$(metro_freshness_verdict "${age}" "${SEUIL_JOURS}")

echo "Dernier run de banc : ${last_iso} (source : ${source_desc})"
echo "Âge : ${age} jour(s) — seuil : ${SEUIL_JOURS} jour(s)"

if [ "${verdict}" = frais ]; then
    echo "✓ Preuve de banc fraîche."
    exit 0
fi

echo "::warning::Preuve de banc périmée (${age} j > ${SEUIL_JOURS} j) — relancer le banc et committer le run."
exit 1
