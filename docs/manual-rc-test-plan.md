# Manual release-candidate test plan

Target: `v0.1.0-beta.1`

Run this plan on a separate Windows 11 computer that has access to Google
Health, Claude CLI, and Telegram. The development computer is intentionally
limited to source changes, automated tests, linting, and package builds.

Use a private Telegram chat and real health data only for this private release
candidate test. Never attach `.env`, OAuth files, database files, raw health
exports, complete logs, or real reports to a public issue or repository.

## Result notation

Mark every check with one of these results:

- `PASS` — observed result matches the expected result.
- `FAIL` — observed result differs; record a short sanitized description.
- `BLOCKED` — an external account, permission, or service prevented the test.

For failures, save the command, local time, app version, and a redacted log
excerpt. Remove tokens, chat IDs, file-system usernames, health values, report
text, and OAuth details before sharing the excerpt.

## 1. Release candidate and clean installation

1. Stop any existing OwnVitals process.
2. Clone the exact release-candidate revision into a new folder. Do not reuse
   an existing `.venv`, `data`, `logs`, or OAuth token.
3. Confirm Python 3.12:

   ```powershell
   py -3.12 --version
   ```

   Expected: Python `3.12.x`.

4. Create the environment and install OwnVitals:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
   ```

5. Run the reproducible checks:

   ```powershell
   .\.venv\Scripts\python.exe -m ruff check .
   .\.venv\Scripts\python.exe -m pytest -q
   .\.venv\Scripts\python.exe -m build
   ```

   Expected: Ruff passes, all tests pass, and both a wheel and source archive
   appear in `dist`.

## 2. Private configuration preflight

1. Copy `.env.example` to `.env` and fill only the documented values.
2. Add the Google OAuth client JSON outside Git-tracked paths or in an ignored
   private path.
3. Configure a private Telegram bot and your own numeric chat ID.
4. Confirm that Claude CLI works as the same Windows user:

   ```powershell
   claude --version
   claude -p "Reply with only: OK"
   ```

   Expected: a version is printed and the second command returns `OK`.

5. Initialize the database and inspect resolved non-secret paths:

   ```powershell
   .\.venv\Scripts\python.exe -m fitbit_report.cli init-db
   .\.venv\Scripts\python.exe -m fitbit_report.cli status
   ```

   Expected: no `python-dotenv could not parse` warnings, database
   initialization succeeds, and every displayed path points to the intended
   private location.

## 3. Google Health authorization and baseline

1. Complete OAuth:

   ```powershell
   .\.venv\Scripts\python.exe -m fitbit_report.cli google-health-auth
   ```

   Expected: consent completes and the local token file is created. The token
   must remain ignored by Git.

2. Synchronize one complete day:

   ```powershell
   .\.venv\Scripts\python.exe -m fitbit_report.cli sync --date YYYY-MM-DD
   ```

   Use yesterday's date. Expected: status `success`; logs show fetched and
   normalized records without credentials or raw API responses.

3. Load enough history for a useful personal baseline:

   ```powershell
   .\.venv\Scripts\python.exe -m fitbit_report.cli google-health-backfill --days 30
   ```

   Expected: the backfill completes without a failed day. A 90-day backfill is
   optional when the account has sufficient history.

4. Run the same one-day sync again.

   Expected: it remains successful and does not create uncontrolled duplicate
   records.

## 4. Russian end-to-end report

1. Set `APP_LOCALE=ru` in `.env`.
2. Run:

   ```powershell
   .\.venv\Scripts\python.exe -m fitbit_report.cli test-report
   ```

3. Verify the command:

   - Google Health synchronization succeeds.
   - Claude returns a valid report without schema errors.
   - A Markdown report is saved in the configured report directory.
   - The command finishes with `Telegram delivery: sent`.

4. Verify Telegram:

   - one rich report is received, followed only by feedback controls when they
     are applicable;
   - there is no redundant automatic-report header;
   - title, date, metric table, main takeaway, chart, observations,
     recommendations, experiment, and reliability are present;
   - the report contains no emoji;
   - the chart is placed between the main takeaway and observations;
   - the chart has no cropped labels or values;
   - the daily chart shows signed contributions to the readiness score rather
     than repeating the metric table;
   - positive and negative contributions are distinguishable by position,
     sign, and color, and the displayed contributions reconcile with the final
     readiness score;
   - all observations, recommendations, and experiments from the saved report
     are present in Telegram;
   - feedback buttons refer to the same numbered uncertain observations.

5. Compare Telegram on current desktop and mobile clients if both are
   available. Record the client versions if their rendering differs.

## 5. English end-to-end report

1. Set `APP_LOCALE=en` and restart every OwnVitals process.
2. Run `test-report` again.
3. Repeat all report checks from section 4.
4. Confirm that navigation, delivery copy, table labels, chart labels, report
   headings, empty states, and feedback controls contain no unintended Russian
   text. Product names and source-specific technical terms may remain as-is.

After the test, restore the preferred locale and restart the application.

## 6. Telegram workflows

Start the application:

```powershell
.\.venv\Scripts\python.exe run.py
```

Verify in each supported locale:

- `/start`, main menu, Help, Status, and Usage;
- one journal note, meal-time entry, morning check-in, and evening check-in;
- the **Add food** flow with photo only, description only, exact calories and
  macros only, and a combined photo plus description; verify every optional
  step can be skipped and entered exact values remain unchanged in the review;
- one Claude question;
- manual synchronization;
- daily report archive opening;
- cancellation and back-navigation from an in-progress flow;
- unauthorized chat IDs cannot use the bot;
- only one polling process is running.

Expected: every completed input is acknowledged once, navigation returns to a
usable menu, and no private traceback is sent to Telegram.

## 7. Delivery fallback and recovery

The rich-delivery fallback is covered automatically by the test suite. A
manual destructive Telegram API simulation is not required for the beta.

Perform one safe recovery check instead:

1. Stop OwnVitals normally with `Ctrl+C`.
2. Temporarily disconnect the network.
3. Start OwnVitals and request or wait for a synchronization.
4. Restore the network and trigger synchronization again.

Expected: the failed attempt is logged without process corruption, and the
next attempt succeeds without recreating the database or OAuth setup.

## 8. Backup and restore copy

1. Create a backup:

   ```powershell
   .\.venv\Scripts\python.exe -m fitbit_report.cli backup
   ```

2. Copy the archive to a temporary private folder.
3. Inspect the archive and confirm it contains the expected local application
   data.
4. Restore the copy into a separate temporary OwnVitals installation or
   directory; do not overwrite the working installation.
5. Start the restored copy without enabling a second Telegram polling process
   and verify that the database and saved reports can be read.

Expected: the backup is usable and the test does not expose it to Git or cloud
storage unintentionally.

## 9. Privacy and public-artifact review

Before publishing screenshots or examples:

- generate them from synthetic data only;
- inspect visible names, paths, dates, chat IDs, usernames, health values, and
  report prose;
- inspect image metadata;
- confirm `.env`, OAuth credentials, tokens, databases, logs, real reports,
  backups, and raw exports are absent from `git status` and the staged file
  list;
- run the repository secret scan and let all GitHub Actions jobs pass.

## 10. Completion record

Record only this sanitized summary for the release decision:

```text
Revision:
Windows version:
Python version:
Telegram Desktop version:
Telegram mobile version (optional):
Russian E2E: PASS / FAIL / BLOCKED
English E2E: PASS / FAIL / BLOCKED
Menus and journal: PASS / FAIL / BLOCKED
Recovery: PASS / FAIL / BLOCKED
Backup/restore: PASS / FAIL / BLOCKED
Privacy review: PASS / FAIL / BLOCKED
Notes (no personal data):
```

The release candidate passes only when every item is `PASS`, or a remaining
limitation is deliberately documented in the beta release notes.
