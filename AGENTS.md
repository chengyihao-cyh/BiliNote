# BiliNote personal fork

This repository is the public application fork. Before making changes:

- Read `CLAUDE.md` for architecture and local development commands.
- Read `doc/CUSTOM_FORK.md` for the personal branch, CI, image, upstream-sync,
  and deployment contract. It overrides generic upstream release guidance for
  this fork.
- Read `doc/DEPLOYMENT.md` before changing images, health checks, persistent
  storage, backup behavior, or application deployment.

## Development contract

- Do not push directly to `master`. Create a short-lived branch such as
  `feature/*`, `fix/*`, or `chore/*` and merge through a pull request.
- Keep commits compatible with `.commitlintrc.json`.
- Required checks are `Backend tests`, `Frontend checks and build`, and
  `Lint commit messages`.
- `master` is the deployable integration branch. A merge publishes an immutable
  GHCR image that the home server may automatically deploy within five minutes.
- Keep generic upstreamable fixes separate from personal features when
  practical so scheduled upstream syncs remain reviewable.

## Validation

- Backend changes: run the focused tests and the stable backend suite described
  in `.github/workflows/ci.yml`.
- Frontend changes: run `pnpm lint` and `pnpm build` in `BillNote_frontend`.
  Existing upstream lint debt is reported but currently non-blocking in CI; do
  not introduce new lint failures in changed code.
- Workflow or image changes: inspect both `.github/workflows/homelab-image.yml`
  and `doc/DEPLOYMENT.md` before changing tags, labels, ports, health checks, or
  volume paths.
- Homelab runtime changes: validate every shell script with `bash -n` and the
  Compose file with `docker compose config` before running
  `deploy/homelab/install.sh`.

## Boundaries

- Never commit API keys, cookies, `.env` files, production databases, server
  credentials, private network details, or copied user data.
- Do not add SSH-based GitHub deployment. Delivery must remain pull-based.
- Do not change or remove the four persistent volume mount paths without an
  explicit data migration plan and a verified backup.
- Application changes do not authorize a production deployment or live data
  mutation unless the user explicitly requests it.
