#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get upgrade -y
apt-get install -y curl awscli nano procps tmux jq parallel gnupg apt-transport-https sudo wget filebeat

# Node.js
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
# shellcheck source=/dev/null
source /root/.bashrc
npm install --lts

# pnpm
export SHELL=bash
curl -fsSL https://get.pnpm.io/install.sh | sh -

# Python package manager (uv)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Elasticsearch APT repository
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
echo "deb https://artifacts.elastic.co/packages/9.0/apt stable main" \
    | sudo tee -a /etc/apt/sources.list.d/elastic-9.0.list
