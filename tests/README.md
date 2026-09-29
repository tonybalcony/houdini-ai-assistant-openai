# Tests

`unit/` contains offline regressions with dummy credentials and disposable storage. Run `python -m unittest discover -s tests/unit -t .` from the repository root. Windows DPAPI needs a normal profile; symlink creation may be unavailable.

`integration/` contains explicit opt-in native/Qt/render/model checks. See [Development](../docs/DEVELOPMENT.md) before running them: native checks need a Houdini license, and `--live` can consume subscription or paid API usage. Do not run everything recursively. Shared fixtures are in `support.py`; output goes into ignored `.local/checks`.

0.6 removes the old upstream MCP/texture tests and native-rollout restart check because those runtimes/tools no longer ship. Scene-scoped storage, ephemeral-context restoration, checked paths, offline bundle tamper/consent and Codex isolation have dedicated regressions.
