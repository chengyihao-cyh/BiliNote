#!/usr/bin/env bash
set -euo pipefail

remote_dir=${REMOTE_DIR:-/home/cyh/bilinote}
backup_dir=${BACKUP_DIR:-$remote_dir/backups}
backup_retention=${BACKUP_RETENTION:-5}
timestamp=$(date +%Y%m%d-%H%M%S)
backup_name=bilinote-data-$timestamp.tar.gz
image=$(docker inspect bilinote --format '{{.Config.Image}}')
was_running=$(docker inspect bilinote --format '{{.State.Running}}')

if [[ ! $backup_retention =~ ^[1-9][0-9]*$ ]]; then
  printf 'BACKUP_RETENTION must be a positive integer: %s\n' \
    "$backup_retention" >&2
  exit 2
fi

install -d -m 0700 "$backup_dir"

restart_container() {
  if [[ $was_running == true ]] && \
    [[ $(docker inspect bilinote --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    docker start bilinote >/dev/null
  fi
}
trap restart_container EXIT

if [[ $was_running == true ]]; then
  docker stop bilinote >/dev/null
fi

docker run --rm \
  -v bilinote-data:/source/data:ro \
  -v bilinote-config:/source/config:ro \
  -v bilinote-static:/source/static:ro \
  -v "$backup_dir":/backup \
  --entrypoint python "$image" -c \
  'import sys, tarfile
with tarfile.open(sys.argv[1], "w:gz") as archive:
    for name in ("data", "config", "static"):
        archive.add("/source/" + name, arcname=name)' \
  "/backup/$backup_name"

restart_container
trap - EXIT

mapfile -t backups < <(
  find "$backup_dir" -maxdepth 1 -type f \
    -name 'bilinote-data-*.tar.gz' -printf '%T@ %p\n' |
    sort -rn
)
for ((index = backup_retention; index < ${#backups[@]}; index++)); do
  rm -f -- "${backups[index]#* }"
done

printf '%s/%s\n' "$backup_dir" "$backup_name"
