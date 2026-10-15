# Personal fork operations

This fork keeps personal BiliNote features separate from generic server
infrastructure. Application code, image builds, Compose, persistent-volume
contracts, backups, deployment, and rollback live here. Host networking, Docker
and NVIDIA setup, reverse proxying, TLS, and shared monitoring stay in the
homelab repository.

For coding-agent context, start with the repository root `AGENTS.md` and
`CLAUDE.md`. The application deployment contract is documented in
`doc/DEPLOYMENT.md`. Do not copy server credentials or production data into this
public repository.

## Git model

- `origin`: `git@github.com:chengyihao-cyh/BiliNote.git`
- `upstream`: `git@github.com:JefferyHcool/BiliNote.git`
- `master`: deployable personal integration branch
- `feature/*`, `fix/*`, and `chore/*`: short-lived branches merged through pull requests
- `sync/upstream-master`: automation-owned branch used only for upstream sync PRs

Do not develop directly on `sync/upstream-master`. Generic fixes should be kept
small enough to submit upstream later.

## Protected master

`master` is protected for the repository owner as well as other contributors:

- changes must arrive through a pull request;
- no approving review is required for this single-developer fork;
- the branch must be current and pass `Backend tests`,
  `Frontend checks and build`, and `Lint commit messages`;
- direct and force pushes are blocked; and
- branch deletion is blocked.

Do not weaken the rule to make a change pass. Fix or intentionally revise the
relevant CI contract through a reviewed pull request.

## Versioning

`CUSTOM_VERSION` records the application version shown by development images.
Use `<upstream-version>-custom.<revision>`, for example:
`2.4.5-custom.1`.

Normal merges to `master` publish two image tags:

- `ghcr.io/chengyihao-cyh/bilinote:edge`
- `ghcr.io/chengyihao-cyh/bilinote:sha-<full-commit-sha>`

Deployment always uses the immutable SHA tag. `edge` is only a convenience tag.
For named releases, create a tag such as `custom-v2.4.5-custom.1`; this avoids
triggering the upstream desktop and extension release workflows that listen on
`v*`.

## Development flow

```bash
git switch master
git pull --ff-only origin master
git switch -c feature/<scope>-<name>

# develop, test, and commit
git push -u origin HEAD
```

Pull requests to `master` run backend tests plus frontend lint and production
build checks. The upstream 2.4.5 baseline contains existing lint failures, so
lint is reported but is temporarily non-blocking; backend tests and the frontend
production build are blocking. Two upstream backend test files are also reported
separately: the serial-executor test contradicts the current concurrent
implementation, and the yt-dlp retry test pollutes `sys.modules` when run in the
full suite. The remaining backend suite is blocking. A merge to `master` builds
and publishes the CUDA-enabled amd64 image. The image build remains compatible
with CPU-only builds because CUDA is controlled by the `INSTALL_CUDA` Docker
build argument.

`RELEASING.md` describes the upstream project's release-manager flow. For this
personal fork, this document is authoritative when its branch, tag, or review
rules differ.

## Syncing upstream

The scheduled `Propose Upstream Sync` workflow runs every Monday at 11:17
Asia/Shanghai time. It opens or updates a PR; it never merges upstream code into
`master` automatically. A merge conflict intentionally fails the workflow so it
can be resolved locally.

For a manual sync:

```bash
git fetch upstream master --tags
git switch master
git pull --ff-only origin master
git merge --no-edit upstream/master
```

Run CI locally, resolve any custom-code conflicts, then push through a normal PR.

## Deployment controls

The homelab uses pull-based deployment, so GitHub has no SSH key or network
access to the server. The image workflow only publishes images to the public
GHCR package. Every five minutes, the server pulls `edge`, reads its
`org.opencontainers.image.revision` label, and deploys the corresponding
immutable `sha-<full-commit-sha>` tag when it changes.

The server-side deployment scripts in `deploy/homelab/`:

- allow only images matching
  `ghcr.io/chengyihao-cyh/bilinote:sha-<40-character-commit-sha>`;
- verify that PyTorch and CTranslate2 can use the GPU before switching;
- take a cold backup of the data, config, and static volumes;
- preserve all four external volumes; and
- restore the prior image automatically if startup or health checking fails.

The polling task runs from the `cyh` user crontab and uses a deployment lock to
prevent overlapping manual or automatic releases. No repository Actions secrets
or deployment variables are required.

After changing the runtime files, run `deploy/homelab/install.sh` from a trusted
checkout. It validates and installs the files under `/home/cyh/bilinote` without
touching `.env`, backups, or Docker volumes and without forcing an image switch.

Application changes stop at image publication unless a deployment is explicitly
requested. Generic host networking, TLS, reverse proxying, and monitoring are
managed outside this application repository. The application-specific runtime
contract and data-preservation rules remain documented here in
`doc/DEPLOYMENT.md` so BiliNote development does not depend on another project's
documentation.

A code change is not permission to mutate production data or to deploy manually
unless the user explicitly asks for that operation.
