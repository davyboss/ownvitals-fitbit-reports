# Privacy and data flow

OwnVitals is self-hosted. The project author does not operate a server, collect
telemetry, receive your health data, or have access to your installation.

## Data stored locally

Depending on the enabled features, the application stores:

- Google Health activity, sleep, body, heart, and workout records;
- journal entries, productivity check-ins, nutrition data, and feedback;
- FatSecret OAuth tokens, imported diary data, and optional source PDFs;
- food, training, and question photos;
- generated reports, personal baselines, Claude prompts/responses and usage
  metadata;
- operational logs and local ZIP backups.

The main store is SQLite. Additional files are written to the configured
`data`, `logs`, backup, photo, FatSecret report, and Obsidian directories.
Deleting the repository alone does not delete paths configured outside it.

## Data sent to third parties

- **Google Health:** OAuth and API requests retrieve the scopes you explicitly
  configure. The default scopes are read-only.
- **Telegram:** messages, photos, status replies, and generated reports pass
  through Telegram's service and are subject to Telegram's privacy policy.
- **Claude CLI:** report context, questions, selected health/journal data, and
  attached images may be sent using the locally authenticated Claude CLI. The
  exact handling depends on your Anthropic account and plan.
- **FatSecret:** optional OAuth/API requests access your food diary. Manual PDF
  imports are processed locally after Telegram has transported the attachment.
- **Obsidian/sync:** reports are written to the configured vault. Any Obsidian
  Sync or third-party folder synchronization is controlled by you.

OwnVitals has no built-in analytics or advertising SDK.

## Retention and deletion

Retention is controlled by the operator. The application does not currently
apply automatic retention limits to the SQLite database, reports, photos,
logs, imported PDFs, or backups. To remove data, stop the process and delete
the relevant configured files and directories. Revoke Google and FatSecret
access and rotate the Telegram bot token when decommissioning an installation.

Review synchronized Obsidian copies, Telegram chat history, provider account
history, and off-device backups separately; deleting local files cannot erase
copies held by those services.

## Safe public sharing

Use synthetic data for screenshots, demos, bug reports, and contributions.
Health records can remain identifying even after names are removed. Inspect
images, report text, timestamps, paths, and metadata before sharing them.

## Medical limitation

OwnVitals provides personal summaries and hypotheses, not medical advice,
diagnosis, monitoring, or emergency support. Consult a qualified professional
for health decisions.
