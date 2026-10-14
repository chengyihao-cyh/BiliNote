# Personal fork operations

This fork keeps personal BiliNote features separate from homelab infrastructure.
Application code and image builds live here; host networking, persistent volumes,
reverse proxying, monitoring, and rollback orchestration stay in the homelab repo.

## Git model

- `origin`: `git@github.com:chengyihao-cyh/BiliNote.git`
- `upstream`: `git@github.com:JefferyHcool/BiliNote.git`
- `master`: deployable personal integration branch
- `feature/*` and `fix/*`: short-lived work branches merged through pull requests
- `sync/upstream-master`: automation-owned branch used only for upstream sync PRs

Do not develop directly on `sync/upstream-master`. Generic fixes should be kept
small enough to submit upstream later.

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

The image workflow's deployment job is disabled until the following repository
configuration exists:

- Variables: `AUTO_DEPLOY`, `DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER`
- Secrets: `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`
- A server-side forced-command SSH key that can invoke only the BiliNote deploy
  script

Keep `AUTO_DEPLOY` set to `false` until an immutable image has been pulled and
verified manually. The deployment script owns health checking and rollback; the
GitHub workflow only passes the exact image reference to it.
