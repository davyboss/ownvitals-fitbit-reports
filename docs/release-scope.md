# OwnVitals for Fitbit & Pixel Watch public beta scope

## Product identity

**OwnVitals for Fitbit & Pixel Watch** is a self-hosted health reporting and
personal insight agent for people whose wearable data is available through
Google Health.

Public tagline:

> Self-hosted health reports. Your data. Your baseline. Your insights.

The existing Python package name, CLI command, and database identifiers remain
`fitbit_report` for the beta. Renaming internal identifiers is deliberately
deferred to avoid an unnecessary migration and compatibility risk.

## Target release

The first public release is `v0.1.0-beta.1`. It is a portfolio-quality,
single-user application for technically comfortable self-hosters. It is not a
hosted service, medical device, or diagnostic tool.

## Supported beta configuration

- Fitbit and Pixel Watch data through the Google Health API.
- Windows 11 as the primary, tested runtime platform.
- Linux on a best-effort basis and in continuous integration.
- Python 3.12.
- Telegram as the primary user interface.
- Claude CLI as the supported LLM runtime.
- SQLite for local application data.
- English and Russian application locales.
- Obsidian report export as an optional integration.
- FatSecret API and PDF import as optional integrations.

## Explicitly out of scope

- A hosted or commercial SaaS offering.
- Multiple users or shared deployments.
- A web or mobile application.
- Centralized Google OAuth credentials.
- Apple Health, Garmin, Oura, Whoop, or other wearable providers.
- A general-purpose LLM provider framework.
- Docker as a supported installation method for the beta.
- Renaming the existing Python package, CLI executable, or database tables.
- Medical diagnosis, treatment recommendations, or emergency guidance.

## Public repository strategy

The historical development repository remains private. The reviewed,
secret-scanned snapshot repository is
[`ownvitals-fitbit-reports`](https://github.com/davyboss/ownvitals-fitbit-reports)
and starts from a new root commit without the private development history.

After the public beta launches, `ownvitals-fitbit-reports` becomes the
canonical repository for future development. The historical repository is
retained as a read-only private archive.

## Release gates

The beta is ready only when all of the following are true:

- A clean checkout installs using the documented instructions.
- The full automated test suite passes on Windows and Linux.
- Lint, package build, dependency audit, and secret scanning pass in CI.
- The current snapshot contains no credentials or personal health data.
- Google Health to SQLite to Claude to Obsidian and Telegram is verified end to
  end.
- English and Russian interfaces contain no unintended mixed-language output.
- Privacy, security, data storage, and medical limitations are documented.
- Public screenshots and example reports use synthetic data only.
- The README explains prerequisites, setup, operation, troubleshooting, and
  removal without requiring private assistance from the author.
- A release candidate has been tested from a fresh Windows installation.

## Scope-change rule

New features that do not directly satisfy a release gate are deferred until
after `v0.1.0-beta.1`. Bugs, privacy issues, installation failures, and incomplete
localization remain in scope.
