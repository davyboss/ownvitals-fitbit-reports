# Start OwnVitals automatically on Windows

OwnVitals includes its own scheduler. Windows Task Scheduler should start one
long-running `run.py` process after sign-in or system startup; do not create
separate scheduled tasks for synchronization, reports, or backups.

## Before creating the task

Complete the installation and one-time authorization from the project
directory, then verify the full workflow:

```powershell
.\.venv\Scripts\python.exe -m fitbit_report.cli google-health-auth
.\.venv\Scripts\python.exe -m fitbit_report.cli test-report
```

## Task Scheduler settings

Create a task for the same Windows account that owns the project and its OAuth
files. Configure:

- **Trigger:** At log on, or at startup if the account and Claude
  authentication work in that mode.
- **Program/script:** the absolute path to
  `.venv\Scripts\python.exe` inside the project.
- **Add arguments:** `run.py`
- **Start in:** the absolute path to the OwnVitals project directory.
- **Restart on failure:** enabled with a reasonable delay, such as one minute.
- **Do not start a new instance:** enabled if the task is already running.

The working directory is required because `.env` and the default `data/`,
`logs/`, and report paths are resolved from it.

## Verify the task

Run the task manually once, send `/start` to the bot, and inspect the newest
file under `logs/`. Confirm in Task Manager that only one OwnVitals Python
process is running.

To stop automatic startup, end the running task and disable or delete this Task
Scheduler entry. This does not delete any health data or credentials; follow
the removal checklist in the main README when decommissioning OwnVitals.
