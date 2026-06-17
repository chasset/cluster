# Image MLflow **maison** (ADR 0082, amendé) : l'officielle + le driver PostgreSQL.
#
# POURQUOI : l'image officielle `ghcr.io/mlflow/mlflow` est multi-arch (amd64+arm64,
# d'où le choix initial « pas de build maison ») et embarque `boto3` (artefact store
# S3 OK), MAIS PAS `psycopg2` (driver PostgreSQL). Or notre backend store est une base
# CNPG `mlflow` (`--backend-store-uri postgresql://…`) : `mlflow server` crashe alors
# au démarrage sur `ModuleNotFoundError: No module named 'psycopg2'` (CrashLoopBackOff
# vécu, logs du 2026-06-17). On dérive donc une image qui AJOUTE le seul paquet
# manquant — minimal, contrairement à Marquez/Dagster (rebuild arm64 complet).
#
# MULTI-ARCH conservé : on part de l'image officielle (index multi-arch, ADR 0006) et
# on n'ajoute que `psycopg2-binary` (wheels manylinux/aarch64 publiées) → l'image
# dérivée reste amd64 (prod) ET arm64 (banc). Pas de spécificité d'arch (≠ Marquez).
#
# `psycopg2-binary` (LGPL, wheel autoportée libpq incluse) plutôt que `psycopg2`
# (compile contre libpq système, absente de l'image slim) — recommandé MLflow pour un
# conteneur. Pas d'épinglage de version : on suit la résolution de l'image de base
# (Python 3.10) ; l'image FINALE est figée par DIGEST au repin (ADR 0006).
#
# Build (depuis ce dossier — contexte local, comme Dagster) :
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     -t <registry-interne>/mlflow:v3.4.0 --push .
FROM ghcr.io/mlflow/mlflow:v3.4.0@sha256:9c9e24a3fc24a0e9dcc5ba1daa9ebfc59e01b0a23b6eb89a4fdf25b84ad5347c
RUN pip install --no-cache-dir psycopg2-binary
