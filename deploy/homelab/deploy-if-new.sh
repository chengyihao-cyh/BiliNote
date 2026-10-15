#!/usr/bin/env bash
set -euo pipefail

remote_dir=${REMOTE_DIR:-/home/cyh/bilinote}
tracking_image=${BILINOTE_TRACKING_IMAGE:-ghcr.io/chengyihao-cyh/bilinote:edge}
image_repository=ghcr.io/chengyihao-cyh/bilinote

if [[ $tracking_image != "$image_repository:edge" ]]; then
  printf 'Refusing unexpected tracking image: %s\n' "$tracking_image" >&2
  exit 2
fi

if ! pull_output=$(docker pull "$tracking_image" 2>&1); then
  printf '%s\n' "$pull_output" >&2
  exit 1
fi

revision=$(docker image inspect "$tracking_image" --format \
  '{{index .Config.Labels "org.opencontainers.image.revision"}}')
revision=${revision,,}

if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Tracking image has an invalid revision label: %s\n' "$revision" >&2
  exit 1
fi

image=$image_repository:sha-$revision
current_image=$(docker inspect bilinote --format '{{.Config.Image}}' 2>/dev/null || true)

if [[ $current_image == "$image" ]]; then
  exit 0
fi

printf 'New BiliNote image detected: %s (current: %s)\n' \
  "$image" "${current_image:-none}"
exec "$remote_dir/deploy-image.sh" "$image"
