# Security policy

OwnVitals is a single-user, self-hosted application that processes sensitive
health data. It is a public beta, not a hardened multi-user service.

## Supported version

Security fixes are provided for the latest commit on the default branch and
the latest published beta release. Older snapshots are not supported.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this
repository. If that feature is unavailable, open a minimal issue asking for a
private contact channel. Do not include secrets, health data, tokens, exploit
details, or identifying screenshots in a public issue.

Include the affected version, the reachable entry point, expected impact, and
the smallest reproduction that does not contain personal data. You should
receive an acknowledgement within seven days. There is currently no paid bug
bounty.

## Deployment assumptions

- Run one instance for one person and configure a private one-to-one Telegram
  chat ID. Group chats and shared deployments are unsupported.
- Keep the host OS account, Telegram bot token, Google OAuth files, FatSecret
  credentials, SQLite database, logs, photos, reports, and backups private.
- Use the default local paths or another directory accessible only to the
  service user. OwnVitals enforces owner-only POSIX permissions for files it
  creates; on Windows, keep the project under a private user profile and verify
  the inherited NTFS ACLs.
- Do not expose the process as a public network service. The Telegram
  integration uses outbound long polling.
- Imported FatSecret PDFs are limited to 10 MiB, 50 pages, and 1,000,000
  extracted characters. Document parsing is still not a security sandbox; only
  import files you trust.
- Backups are local ZIP archives and are not encrypted. Store and transfer them
  as sensitive health records.

## Secrets and public contributions

Never commit `.env`, OAuth client files, refresh tokens, databases, logs,
backups, photos, PDFs, Obsidian reports, or real health exports. Use synthetic
data in tests, issues, screenshots, and pull requests. If a secret is exposed,
revoke or rotate it; deleting it from a later commit is not sufficient.

## Security boundaries

OwnVitals reduces accidental exposure but does not defend against malware or a
process running as the same OS user. It is not a medical device and should not
be used for diagnosis, emergency decisions, or treatment instructions.
