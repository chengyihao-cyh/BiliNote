# Personal deployment contract

This repository is the durable source of truth for BiliNote-specific
development, CI/CD, image, runtime, and data-preservation knowledge. Generic
server networking, TLS, reverse proxying, and monitoring are managed separately
and should not be changed as part of normal BiliNote feature work.

This is a public repository. Keep credentials, API keys, cookies, SMTP details,
private addresses, production databases, and copied user data out of this file
and out of Git.

## Delivery path

1. Develop on a short-lived branch and open a pull request to protected
   `master`.
2. The pull request must pass the checks documented in `doc/CUSTOM_FORK.md`.
3. A merge to `master` runs `.github/workflows/homelab-image.yml` and publishes
   `edge` plus the immutable `sha-<40-character-commit-sha>` tag to GHCR.
4. The home server polls `edge` every five minutes, reads the OCI
   `org.opencontainers.image.revision` label, and deploys only the matching
   immutable SHA tag.
5. The server validates the image and GPU, creates a cold backup, switches the
   container, waits for health, and restores the previous image if startup or
   health verification fails.

GitHub has no SSH key and no inbound access to the server. Delivery is
pull-based; do not replace it with an SSH push workflow merely for convenience.

The version-controlled runtime implementation is in `deploy/homelab/`. The
files are installed under `/home/cyh/bilinote`; the server does not need a Git
checkout and GitHub does not receive server access.

## Image contract

- Registry: `ghcr.io/chengyihao-cyh/bilinote`
- Tracking tag: `edge`
- Deployment tag: `sha-<full-commit-sha>`
- Platform: `linux/amd64`
- Build file: `Dockerfile.complete`
- CUDA build argument: `INSTALL_CUDA=true`
- Source revision: the OCI `org.opencontainers.image.revision` label

`edge` is a discovery tag, not a rollback-safe deployment reference. Runtime
configuration must resolve and retain the immutable SHA tag.

## Runtime contract

- SSH alias used for local operations: `homelab`
- Server deployment root: `/home/cyh/bilinote`
- Container name: `bilinote`
- Local published port: `127.0.0.1:3015`
- Application health endpoint: `http://127.0.0.1:3015/api/sys_health`
- Automatic deployment log: `/home/cyh/bilinote/auto-deploy.log`
- Deployment lock: `/home/cyh/bilinote/.deploy.lock`
- Backup directory: `/home/cyh/bilinote/backups`

These paths describe the BiliNote application contract. Changes to generic
gateway, certificate, or monitoring configuration belong to the server
infrastructure project instead.

## Runtime installation

After reviewing a change to `deploy/homelab/`, install it from a trusted local
checkout:

```bash
deploy/homelab/install.sh
```

The installer validates shell syntax and the rendered Compose configuration,
atomically replaces the four version-controlled runtime files, and maintains
the five-minute cron entry. It preserves `/home/cyh/bilinote/.env`, the backup
directory, deployment history files, and all Docker volumes. Installing runtime
files does not trigger an image deployment.

## Persistent data

The application depends on four external Docker volumes:

| Volume | Container path | Backup policy |
| --- | --- | --- |
| `bilinote-data` | `/app/backend/data` | Archived before image switches |
| `bilinote-config` | `/app/backend/config` | Archived before image switches |
| `bilinote-static` | `/app/backend/static` | Archived before image switches |
| `bilinote-models` | `/app/backend/models` | Preserved, not archived; models are reproducible |

The default local retention is the five newest successful data archives. A
backup covers data, configuration, and static files. It briefly stops the
container for consistency, restarts it, and only then prunes older archives.

Never use `docker compose down -v`, delete the named volumes, change their mount
paths without a migration, or treat an image rollback as a replacement for a
data backup. Preserving existing user data is the highest-priority deployment
invariant.

## Deployment behavior

The server-side deployment implementation must keep this order:

1. Accept only an image from the expected repository with a full SHA tag.
2. Acquire the deployment lock.
3. Pull the image and verify PyTorch and CTranslate2 can see the NVIDIA GPU.
4. Create a cold backup when replacing an existing container.
5. Preserve the previous image reference and runtime environment.
6. Start Compose and wait for its health check.
7. Query the BiliNote application health endpoint.
8. Restore the previous image if either startup or application health fails.

Application changes that alter image labels, ports, the health response, Docker
paths, user IDs, or volume paths must update this contract and the deployment
implementation together.

## Read-only production checks

Use read-only checks before proposing operational changes:

```bash
ssh homelab 'docker inspect bilinote --format "{{.Config.Image}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}"'
ssh homelab 'tail -n 100 /home/cyh/bilinote/auto-deploy.log'
ssh homelab 'find /home/cyh/bilinote/backups -maxdepth 1 -type f -name "bilinote-data-*.tar.gz" -printf "%TY-%Tm-%Td %TH:%TM %f\n" | sort'
ssh homelab 'docker volume ls --format "{{.Name}}" | grep "^bilinote-" | sort'
```

Do not run a manual deployment or mutate production data unless the user
explicitly requests that action.

## Failure visibility

- Image, GPU, backup, Compose, and health failures exit non-zero.
- Failed container switches restore the previous image.
- Automatic deployment output is retained in `auto-deploy.log`.
- External health monitoring detects application outages.

Direct email delivery for deployment failures has not been configured and
verified. Do not claim it is active until the chosen notification mechanism has
passed a real delivery test. Recipient addresses and mail credentials must be
stored outside this public repository.
