# Changelog

All notable changes to OwnVitals will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0-beta.1] - 2026-09-22

### Added

- English and Russian application locales.
- Public-release privacy, security, contribution, and CI documentation.
- Daily readiness contribution charts that explain the score without
  repeating the metric table.
- A deterministic synthetic demo database generator for screenshots and
  development, plus report generation for an explicit date without syncing.
- Public positioning as OwnVitals for Fitbit & Pixel Watch and the searchable
  `ownvitals-fitbit-reports` repository name.
- Weekly Dependabot checks and CodeQL analysis for the public repository.

### Security

- Pinned every third-party GitHub Action to an immutable commit SHA.
- Restricted FatSecret PDF downloads to direct HTTPS responses without
  following redirects, preventing an approved URL from redirecting to an
  untrusted host.
- Replaced realistic identifiers in test URLs with explicit placeholders.

[Unreleased]: https://github.com/davyboss/ownvitals-fitbit-reports/compare/v0.1.0-beta.1...HEAD
[0.1.0-beta.1]: https://github.com/davyboss/ownvitals-fitbit-reports/releases/tag/v0.1.0-beta.1
