# Release review - 0.4.0 public preview

Prepared 2026-09-27. Remote publication requires the owner's approval.

## Proposed repository

- GitHub slug: `houdini-ai-assistant-openai`
- README title: **Houdini AI Assistant (OpenAI)**
- Visibility: public, after approval
- License: MIT (selected by the owner)
- Default branch: `main`
- Root: this assistant directory, not the surrounding Houdini workspace
- No GitHub remote has been created/configured during preparation

```text
houdini-ai-assistant-openai/
  README.md, LICENSE, VERSION, CHANGELOG.md
  AGENTS.md, ARCHITECTURE.md, DEVELOPMENT.md
  CONTRIBUTING.md, SECURITY.md, THIRD_PARTY.md
  LOOKDEV_AND_DIAGNOSTICS.md, RELEASE_CHECKLIST.md
  .gitignore, .gitattributes
  .github/workflows/validate.yml
  scripts/audit_release.py
  setup.ps1, setup_mcp.ps1, setup_common.ps1
  install_mcp_source.py
  requirements*.txt
  local_settings.example.json
  open_panel.py, panel_install.py, astra.pypanel
  astra_panel.py, codex_worker.py, worker.py
  *_tools.py, *_contracts.py, mcp_*.py
  chat_store.py, diagnostics.py, runtime_settings.py
  texture_*.py, uthana_*.py, render_*.py, asset_worker.py
  test_*.py, check_*.py
```

The flat Python layout preserves the existing Houdini import architecture. Packaging
changes are limited to portable setup/configuration, dependency acquisition, release
metadata and test isolation/fixtures.

## What is included

Original source, scripts, public documentation, MIT license, versioned dependency
lists, empty configuration example, synthetic-fixture tests and a Windows CI workflow.

## What stays private/local

- All keys/credentials, .secrets, environment files, Codex auth/session state.
- Chat history, logs, render jobs, downloaded motion/textures and local settings.
- Python installations/environments, downloaded vendor source and generated protocol dumps.
- Houdini scenes/geometry, renders/media, backups, caches, screenshots and validation output.
- Historical machine-specific lessons/reports and sibling workspace files.

Ignore rules protect these categories, and the source audit inspects only staged
release content. Ignored credential files are not opened or copied to the audit
directory. Gitleaks scans the staged source export and Git history with redaction.
Ignore rules alone are not a substitute for reviewing the exact commit contents.

## Verification

- Fresh local clone with no runtime environments, vendor tree, credentials, chat history
  or private texture settings: full setup succeeded using signed Python 3.13.15.
- Both freshly installed dependency environments: `pip check` passed.
- Offline suite: **55 tests passed** in both the working folder and clean clone.
- Native Houdini 22.0.368: saved-chat/Qt, scene editing, Stop/stale-call guards and
  APEX animation/focus checks passed in disposable processes.
- Native Solaris/MaterialX authoring: passed with synthetic textures.
- Codex ChatGPT sign-in and live MCP tool operations: passed without a model turn;
  46 exposed tools, node edits, Python execution, lookdev tools and reconnect verified.
- The same user's installed Houdini license and Codex sign-in were used; no account
  state was copied into Git. A different user's account and a clean Windows OS were
  not available to test.
- A local OCIO-profile warning appeared during native checks; checks completed.
  No user color settings were changed or included in the repository.
- Remote GitHub Actions has not run yet; its commands were validated locally.
- New renders/image transport, paid API/model calls and Uthana generation were not
  rerun for this packaging change. The MCP image check explicitly reported skipped.
  Existing render/animation behavior is unchanged.

## Before publication

- [ ] Owner approves this structure, slug and public visibility.
- [ ] Choose the GitHub account/organization during publication; do not assume a destination.
- [ ] Install GitHub CLI if needed and authenticate the owner. It was not on PATH during preparation.
- [ ] Recheck clean Git status, source/history scans and exact commit list.
- [ ] Create an empty GitHub repository, set origin and push main.
- [ ] Verify remote HEAD equals local HEAD and review the remote tree/README/license.
- [ ] Check the first CI run and enable private vulnerability reporting if desired.
- [ ] Create a release/tag only when requested; 0.4.0 currently describes the prepared preview.

## Ongoing limitations

Windows/Houdini 22 is the tested target. Both billing modes require each user's own
account/model access. Uthana is optional and separately billed. Fab acquisition is
manual, arbitrary rigs can need mapping, and XPU does not guarantee every GPU driver
works. See the README and architecture guide.

The upstream MCP archive declares MIT in package metadata but lacks a standalone
license notice; source is fetched from upstream rather than redistributed here.
See THIRD_PARTY.md. Dependency vulnerabilities have not been fully audited.
