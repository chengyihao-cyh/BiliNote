# Homelab deployment

This directory is the source of truth for BiliNote's application-specific
runtime. The server uses copies of these files under `/home/cyh/bilinote`; it
does not require a Git checkout.

Run the installer from the repository root after changing any file here:

```bash
deploy/homelab/install.sh
```

The installer validates and atomically replaces the Compose file and deployment
scripts, then ensures the five-minute polling cron entry exists. It does not
replace `.env`, backups, or Docker volumes, and it does not deploy a new image.

Set `REMOTE_HOST` or `REMOTE_DIR` only when targeting a different server or
runtime directory. See `doc/DEPLOYMENT.md` for the complete delivery, data,
backup, and rollback contract.
