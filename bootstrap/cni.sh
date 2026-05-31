#!/usr/bin/env bash
set -euo pipefail

# Idempotent : rejouable sans erreur si le CLI est déjà posé ou si Cilium est
# déjà installé dans le cluster (le banc multi-node le rejoue, et un opérateur
# peut relancer la phase CNI après un échec partiel).

CILIUM_VERSION=1.19.4          # version du composant Cilium (Helm release)
# Cilium CLI (pinned for reproducibility)
CILIUM_CLI_VERSION=v0.19.4
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi

# --- Installer le CLI cilium (idempotent) ---------------------------------
if command -v cilium > /dev/null 2>&1; then
  echo "cilium CLI déjà présent ($(command -v cilium)) — skip download."
else
  TARBALL="cilium-linux-${CLI_ARCH}.tar.gz"
  # Nettoyage préalable : un .tar.gz résiduel d'un run avorté ferait échouer
  # curl --remote-name-all ou le rm final.
  rm -f "${TARBALL}" "${TARBALL}.sha256sum"
  curl -L --fail --remote-name-all "https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/${TARBALL}"{,.sha256sum}
  sha256sum --check "${TARBALL}.sha256sum"
  sudo tar xzvfC "${TARBALL}" /usr/local/bin
  rm -f "${TARBALL}" "${TARBALL}.sha256sum"
fi

# --- Installer / mettre à niveau Cilium dans le cluster (idempotent) -------
# `cilium install` échoue si la release Helm existe déjà
# (« cannot reuse a name that is still in use »). On détecte l'install
# existante via `cilium status` et on bascule sur `upgrade`.
#
# CNI — pin Cilium and use a pod CIDR disjoint from the node network
# (nodes are on 10.67.2.0/22, inside the default cluster-pool 10.0.0.0/8).
CILIUM_ARGS=(
  --version "${CILIUM_VERSION}"
  --set ipam.operator.clusterPoolIPv4PodCIDRList=10.244.0.0/16
)
if cilium status > /dev/null 2>&1; then
  echo "Cilium déjà installé — cilium upgrade (réconciliation des valeurs)."
  cilium upgrade "${CILIUM_ARGS[@]}"
else
  cilium install "${CILIUM_ARGS[@]}"
fi
