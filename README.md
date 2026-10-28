# SIL Test Quality

Shared precommit checks for Python code, documentation, complexity, tests, and coverage. Requires Git and Python 3.12 with venv support. These commands work in Windows PowerShell and Linux shells.

To use the checker run these commands from a consumer repo's root:

```sh
git config --local core.hooksPath .githooks
git config --local sil-test-quality.source https://github.com/bradstein87/sil_test_quality.git
git hook run pre-commit
```

The consumer's pyproject.toml selects the checker version. Private repositories require Git credentials with access.

Checks run automatically with `git commit`. For the full report:

```sh
git hook run pre-commit -- --verbose
```
