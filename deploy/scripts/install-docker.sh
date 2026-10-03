#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo 'Установка Docker требует запуска от root.' >&2
  exit 1
fi
# This is the root-owned operating system file, never operator production.env.
# shellcheck source=/dev/null
source /etc/os-release
if [[ ${ID:-} != ubuntu || ${VERSION_ID:-} != 24.04 ]]; then
  echo 'Поддерживается Ubuntu24.04 LTS.' >&2
  exit 1
fi
if docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo 'Docker Engine и Compose уже доступны; версии и пакеты не изменены.'
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl python3 openssl git util-linux
install -m 0755 -d /etc/apt/keyrings
temporary_key=$(mktemp)
temporary_source=$(mktemp)
trap 'rm -f -- "$temporary_key" "$temporary_source"' EXIT
curl --fail --silent --show-error --max-time 30 https://download.docker.com/linux/ubuntu/gpg -o "$temporary_key"
install -m 0644 "$temporary_key" /etc/apt/keyrings/docker.asc
cat > "$temporary_source" <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
install -m 0644 "$temporary_source" /etc/apt/sources.list.d/docker.sources
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker info >/dev/null
docker compose version
echo 'Docker установлен. Доступ к группе docker равнозначен административному доступу; пользователи автоматически не добавлены.'
