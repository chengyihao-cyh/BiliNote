#!/usr/bin/env bash
set -euo pipefail

remote_host=${REMOTE_HOST:-homelab}
remote_dir=${REMOTE_DIR:-/home/cyh/bilinote}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
stage_dir=$remote_dir/.runtime-next-$(date +%Y%m%d-%H%M%S)-$$
runtime_files=(compose.yaml backup-data.sh deploy-image.sh deploy-if-new.sh)

for file in "${runtime_files[@]}"; do
  if [[ ! -f $script_dir/$file ]]; then
    printf 'Missing runtime file: %s\n' "$script_dir/$file" >&2
    exit 1
  fi
done

bash -n \
  "$script_dir/backup-data.sh" \
  "$script_dir/deploy-image.sh" \
  "$script_dir/deploy-if-new.sh"

ssh "$remote_host" install -d -m 0755 "$remote_dir"
ssh "$remote_host" install -d -m 0700 "$stage_dir"

cleanup() {
  ssh "$remote_host" rm -rf -- "$stage_dir" 2>/dev/null || true
}
trap cleanup EXIT

scp "${runtime_files[@]/#/$script_dir/}" "$remote_host:$stage_dir/"

ssh "$remote_host" bash -s -- "$remote_dir" "$stage_dir" <<'REMOTE'
set -euo pipefail

remote_dir=$1
stage_dir=$2
env_file=$remote_dir/.env
compose_file=$stage_dir/compose.yaml

if [[ ! -f $env_file ]]; then
  printf 'Runtime environment file not found: %s\n' "$env_file" >&2
  exit 1
fi

bash -n \
  "$stage_dir/backup-data.sh" \
  "$stage_dir/deploy-image.sh" \
  "$stage_dir/deploy-if-new.sh"
docker compose --env-file "$env_file" -f "$compose_file" config --quiet

install -m 0644 "$compose_file" "$remote_dir/compose.yaml.next"
install -m 0755 "$stage_dir/backup-data.sh" "$remote_dir/backup-data.sh.next"
install -m 0755 "$stage_dir/deploy-image.sh" "$remote_dir/deploy-image.sh.next"
install -m 0755 "$stage_dir/deploy-if-new.sh" "$remote_dir/deploy-if-new.sh.next"

mv "$remote_dir/compose.yaml.next" "$remote_dir/compose.yaml"
mv "$remote_dir/backup-data.sh.next" "$remote_dir/backup-data.sh"
mv "$remote_dir/deploy-image.sh.next" "$remote_dir/deploy-image.sh"
mv "$remote_dir/deploy-if-new.sh.next" "$remote_dir/deploy-if-new.sh"

cron_tmp=$(mktemp)
trap 'rm -f "$cron_tmp"' EXIT
crontab -l 2>/dev/null |
  grep -Fv "$remote_dir/deploy-if-new.sh" |
  grep -Fv '# BiliNote pull-based deployment' >"$cron_tmp" || true
printf '\n# BiliNote pull-based deployment\n' >>"$cron_tmp"
printf '*/5 * * * * %s/deploy-if-new.sh >> %s/auto-deploy.log 2>&1\n' \
  "$remote_dir" "$remote_dir" >>"$cron_tmp"
crontab "$cron_tmp"

rm -rf -- "$stage_dir"
docker inspect bilinote --format \
  'Installed runtime for {{.Config.Image}} (status={{.State.Status}}, health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}})'
REMOTE

trap - EXIT
printf 'BiliNote runtime files installed in %s:%s\n' "$remote_host" "$remote_dir"
