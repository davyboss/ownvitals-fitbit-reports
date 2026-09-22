# Public beta release checklist

Target: `v0.1.0-beta.1`

This checklist separates checks that can be reproduced locally from checks
that require the final public repository or a real personal installation.

## Automated and repository checks

- [x] Project runtime is isolated on Python 3.12.
- [x] Python support is declared as `>=3.12,<3.13`.
- [x] Ruff passes.
- [x] The complete test suite passes on local Linux with Python 3.12.
- [x] Source distribution and wheel build successfully.
- [x] The wheel and its runtime dependencies install in a fresh environment.
- [x] `pip-audit` reports no known dependency vulnerabilities.
- [x] Gitleaks reports no secrets in the working-tree snapshot.
- [x] CI covers Python 3.12 on Windows and Linux.
- [x] CI builds the package, audits dependencies, and scans for secrets.
- [x] Private runtime files and common credential formats are ignored by Git.
- [x] English and Russian automated localization tests pass.
- [x] README, privacy, security, contribution, changelog, and license files are
  present.

## Manual release-candidate checks

External service and real-device verification is performed on the separate
Windows test computer using the
[manual release-candidate test plan](manual-rc-test-plan.md). The development
computer must not be treated as an integration-test environment.

- [ ] Create a fresh snapshot repository with one new root commit and no
  private Git history.
- [ ] Review the exact file list staged for that root commit.
- [ ] Let all GitHub Actions jobs pass in the snapshot repository.
- [x] Complete every check in the manual release-candidate test plan on the
  separate Windows 11 test computer.
- [x] Capture public screenshots and an example report using synthetic data
  only.
- [x] Review screenshots, report text, paths, timestamps, and image metadata for
  identifying information.
- [ ] Enable GitHub private vulnerability reporting.
- [ ] Create the `v0.1.0-beta.1` release and attach release notes.

## Release decision

Do not publish the beta tag until every manual item above is complete or is
explicitly deferred in the release notes with a clear limitation.
