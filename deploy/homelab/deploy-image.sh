#!/usr/bin/env bash
set -euo pipefail

image=${1:-}
remote_dir=${REMOTE_DIR:-/home/cyh/bilinote}
compose_file=$remote_dir/compose.yaml
env_file=$remote_dir/.env
lock_file=$remote_dir/.deploy.lock

if [[ ! $image =~ ^ghcr\.io/chengyihao-cyh/bilinote:sha-[0-9a-f]{40}$ ]]; then
  printf 'Refusing non-immutable or unexpected image: %s\n' "$image" >&2
  exit 2
fi

if [[ ! -f $compose_file ]]; then
  printf 'Compose file not found: %s\n' "$compose_file" >&2
  exit 1
fi

exec 9>"$lock_file"
if ! flock -n 9; then
  printf 'Another BiliNote deployment is already running.\n' >&2
  exit 75
fi

previous_image=$(docker inspect bilinote --format '{{.Config.Image}}' 2>/dev/null || true)
timestamp=$(date +%Y%m%d-%H%M%S)
env_next=$env_file.next
env_backup=$env_file.backup-$timestamp

docker pull "$image"
docker run --rm --gpus all --entrypoint python "$image" -c \
  'import ctranslate2, torch; assert torch.cuda.is_available(); assert ctranslate2.get_cuda_device_count() > 0; print(torch.cuda.get_device_name(0), torch.version.cuda)'

if [[ -n $previous_image ]]; then
  backup_path=$($remote_dir/backup-data.sh)
  printf 'Data backup: %s\n' "$backup_path"
fi

if [[ -f $env_file ]]; then
  cp -a "$env_file" "$env_backup"
fi
printf 'BILINOTE_IMAGE=%s\n' "$image" >"$env_next"
mv "$env_next" "$env_file"

rollback() {
  if [[ -f $env_backup ]]; then
    cp -a "$env_backup" "$env_file"
  elif [[ -n $previous_image ]]; then
    printf 'BILINOTE_IMAGE=%s\n' "$previous_image" >"$env_file"
  else
    rm -f "$env_file"
  fi

  if [[ -n $previous_image ]]; then
    BILINOTE_IMAGE=$previous_image docker compose \
      --env-file "$env_file" -f "$compose_file" up -d --no-build --wait || true
  fi
}

if ! docker compose --env-file "$env_file" -f "$compose_file" \
  up -d --no-build --wait; then
  rollback
  printf 'Deployment failed; restored image %s\n' "$previous_image" >&2
  exit 1
fi

if ! curl --fail --silent --show-error --max-time 20 \
  http://127.0.0.1:3015/api/sys_health; then
  rollback
  printf 'Health check failed; restored image %s\n' "$previous_image" >&2
  exit 1
fi

printf '\nDeployed %s (previous: %s)\n' "$image" "${previous_image:-none}"
