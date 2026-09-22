# OwnVitals v0.1.0-beta.1

The first public beta of OwnVitals: a self-hosted assistant that turns Fitbit
and Pixel Watch health data into detailed personal reports delivered through
Telegram.

## Highlights

- Daily and weekly health reports based on personal baselines.
- Google Health data import for Fitbit and Pixel Watch data.
- English and Russian interfaces and reports.
- Telegram journal, check-ins, questions, and manual meal logging with optional
  photos.
- Optional FatSecret diary import.
- Readiness contribution chart that explains what changed the daily score.
- Synthetic demo data generator for safe screenshots and development.

## Privacy and security

OwnVitals is designed for one trusted user and runs on infrastructure you
control. Health data and credentials remain in the local installation unless
they are sent to a configured external service to provide a requested feature.
Review the [privacy guide](privacy.md), [security policy](../SECURITY.md), and
configuration documentation before connecting personal accounts.

This release pins GitHub Actions to immutable commits, runs secret scanning,
dependency auditing and CodeQL in CI, and restricts FatSecret PDF downloads to
direct HTTPS responses from approved hosts.

## Beta limitations

- This is a personal wellness tool, not a medical device or a substitute for
  professional medical advice.
- The current deployment model is single-user and self-hosted.
- Windows file permissions depend on the operator configuring the host and
  account securely.
- Backups are not encrypted by OwnVitals; store them on encrypted media or in
  an encrypted backup system.
- Claude and connected providers receive only the data required for the
  features you enable, subject to their own policies.

Installation and configuration instructions are available in the
[README](../README.md).
