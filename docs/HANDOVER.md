# Handover — Houdini AI Assistant 0.6.0

Prepared 2026-09-30. Read this with [AGENTS.md](../AGENTS.md), [Architecture](ARCHITECTURE.md), [Development](DEVELOPMENT.md), [Security](../SECURITY.md) and [Release checklist](RELEASE_CHECKLIST.md).

## Current state and destinations

- Implementation commit: `8782076` (`Prepare v0.6.0 with contained installation and checked scene tools`). The following handover commit changes documentation only. Use `git log -1` for the current handover revision.
- Version: **0.6.0 release candidate**, Windows x64; native development/testing host: Houdini **22.0.368**.
- GitHub: [tonybalcony/houdini-ai-assistant-openai](https://github.com/tonybalcony/houdini-ai-assistant-openai), branch `main`, remote `origin`.
- VPS: SSH host alias `agent-hub`, checkout `/srv/projects/houdini_ai_assistant`, branch `main`, local remote `vps`. The VPS checkout accepts a clean fast-forward push using `receive.denyCurrentBranch=updateInstead`.
- The owner authorized pushing source and this handover to both existing remotes on 2026-09-30. Verify both branch hashes after pushing. Do not force-push or overwrite a dirty VPS checkout.
- The tested installer and checksum are now published as [pre-release v0.6.0-rc.1](https://github.com/tonybalcony/houdini-ai-assistant-openai/releases/tag/v0.6.0-rc.1) on 2026-09-30. GitHub's reported asset digest matches the checksum below. The tag targets implementation commit `8782076`; later documentation lives on `main`. The same installer is retained on the VPS under `.local/releases/v0.6.0-rc.1/`, outside Git history.
- Original source is MIT. Runtime components retain their own licenses and notices.

## Owner decisions: do not undo these

The owner initially considered unrestricted tools with warnings, then explicitly chose **folder restriction over unrestricted execution**. That final choice is authoritative.

1. Allow assistant data in the installed plugin and the current saved scene's `$HIP`; reject outside paths even when the user supplies or authorizes them in a prompt.
2. Use checked Houdini tools; remove arbitrary Python, shell and VEX execution. Unsupported operations return an explanation; there is no bypass mode.
3. Remove texture search/download/generation/binding and external texture-library integration.
4. Keep installation self-contained. Show an unchecked consent box before setup. No first-run package downloads, pip, OS installer, registry edits or PATH changes.
5. Keep subscription authentication inside the plugin. Do not reuse another app's Codex account/profile. Ask before any future unavoidable external account-store exception.
6. Chats belong to one saved scene filename. An untitled scene's conversation stays in memory and is discarded when its scene/panel closes.
7. Preserve Solaris lighting, MaterialX materials, Karma XPU rendering, cheap working renders and WIP inspection. Do not substitute Mantra or another renderer.

The filesystem policy is an application boundary, not an OS sandbox around Houdini, its existing scripts/plugins, operating-system dependencies or hostile same-user processes. Do not advertise complete process isolation.

## What changed in this version

### Installation and accounts

- `.runtime/` contains portable Python **3.13.15**, Codex **0.157.1**, and **40 pinned Python distributions**. This is an embeddable interpreter with relative search paths, not a relocated virtual environment.
- `bootstrap.py` only verifies local file hashes, signed Python/Codex publishers and imports. Missing/corrupt files fail closed; it never downloads replacements.
- `setup_ui.py` presents the bundled components, storage/network plan and required consent checkbox. It supports browser subscription sign-in or a masked API-key field and remembers the chosen backend.
- `codex_paths.py` resolves only the bundled executable. `codex_policy.py` uses a private profile, disables native shell/file/app/browser/MCP tooling and starts threads with no execution environments.
- `user_account.py` stores preferences and DPAPI-encrypted API keys inside `.state/account`. Native Codex uses its own file store in `.state/codex`; this project does not encrypt that native sign-in file.
- Global account, executable, chat-directory and API-key lookup fallbacks were removed. Never inspect, migrate or package existing credentials as a maintenance shortcut.
- Child temp files stay inside `.state/tmp`. Houdini child preferences use `.state/houdini__HVER__`; **the `__HVER__` token is required** or Houdini ignores the override. External OCIO/profile/plugin overrides are stripped from the worker environment.

### Tool and filesystem enforcement

- `access_policy.py` derives the scene scope from actual Houdini state (or the panel's internal scene environment for workers). It resolves paths and denies escapes, network paths, private stores, device names and ambiguous Windows paths.
- Relative scene assets resolve under saved `$HIP`. Model-requested writes to plugin program files are denied. Internal installation/account/cache operations use separate checked storage helpers.
- Prompt checks provide early feedback, but individual tools must enforce file boundaries independently. Do not rely on model instructions for access control.
- `scene_policy.py` allows a conservative set of native types and verifies their definitions against the Houdini installation before creation/cooking. It rejects modified/custom HDAs, callbacks and unsupported graphs.
- Specific, unchanged native template computations are allowed for normal Houdini behavior, such as camera conversion and APEX timing. The checker verifies expressions and their languages; spare/modified expressions do not inherit this exception.
- MaterialX builder inheritance fields are frozen to literals. Preferred node versions are resolved and verified before exact creation.
- The unrestricted upstream Houdini MCP/RPyC bridge and all texture modules/configuration/tests were removed. The Agents SDK can still have MCP-related transitive libraries; their presence does not mean an MCP server is started.

### Conversations and recovery

- `ChatStore()` uses `$HIP/.astra/<scene-id>/chats.sqlite3`, with one ID per normalized scene filename. Two files in one directory have separate histories.
- Untitled scenes use in-memory SQLite. First Save preserves visible conversation/draft. Save As switches to the new filename's store; it does not copy the original history automatically.
- Move the `.astra` sidecar directory with the project to keep chats and generated assets. Renaming a scene alone does not remap its history.
- Subscription threads are ephemeral. Reconnect supplies up to the latest **80,000 characters of visible history** as untrusted context on the next explicit prompt. Native hidden rollouts/reasoning are not restored; stale saved native thread IDs are ignored.
- API mode preserves serialized checkpoints. When first saving a previously untitled chat without an API checkpoint, visible text can provide historical context.
- Unsent drafts and interrupted requests are never automatically replayed. Run/call IDs, duplicate suppression, Stop and scene-generation guards remain in place.

### Animation and look development

- APEX tools support verified factory rig chains; the tested rig is Electra. Arbitrary custom graphs are intentionally refused.
- Uthana receives text/settings only. Motion downloads and request recovery state are scene-local. No scene/rig/geometry uploads were added.
- Retargeting keeps its procedural inspection branch but copies only animation data onto a separate Scene Animate connected to the original verified rig. Subsequent APEX edits do not need to trust the retarget branch. Changes to that branch require a new bake.
- Render jobs and flattened USD snapshots live under the saved scene. The supervisor revalidates executable, snapshot and output paths before launching fixed Karma XPU commands.
- Working renders cap resolution/sampling/ray depth and disable costly features in the snapshot. WIP previews and cancellation were exercised with a real render.
- Fixed a Windows file-sharing race: a brief status-reader lock now causes a bounded retry of atomic state-file replacement, instead of aborting a healthy render.

## Storage and distribution

| Location | Purpose | Commit/distribute? |
|---|---|---|
| Root modules, `toolbar/`, package JSON, documentation | Plugin source and UI registration | Git and installer |
| `tests/`, `scripts/`, `.github/` | Tests, maintainers' build/audit tools, CI | Git only |
| `.runtime/` | Verified portable software and licenses | Installer only; ignored by Git |
| `.state/` | Accounts, setup marker, generated panel, logs, temp and child preferences | Never distribute |
| `$HIP/.astra/<scene-id>/` | Chats, generated motion, render jobs and previews | User project data; never bundle |
| `.local/checks/`, `.local/build-downloads/`, `dist/` | Local evidence, build inputs and release artifact | Ignored maintainer data |
| Old `.chat_history/`, `motion_cache/`, texture caches, old environments | Existing local data | Preserved; not migrated, deleted or bundled |

Sibling scenes, geometry, renders, backups and unrelated workspace files were not deleted or included. A used plugin folder must never be zipped for distribution.

## Verified installer artifact

The artifact built from implementation commit `8782076` is:

- `dist/houdini-ai-assistant-0.6.0.zip`
- **203,464,388 bytes** (about 194 MiB)
- SHA-256: `92616aa9cc7faf79fd237fe6b4ca6613dcb90be4da926dd0cbebf0d5ad70603d`
- **4,025 ZIP entries**, including **3,973 manifest-listed runtime files**.
- Companion checksum: `dist/houdini-ai-assistant-0.6.0.zip.sha256`.

This handover and the publication links were added after the installer build; they change no runtime behavior and are available in Git. A rebuilt archive including newer documentation will have a different checksum. Preserve the source revision and checksum for whichever artifact is actually published.

Install the complete plugin asset through Houdini's **File > Install Package Archive...**, or extract it into the user's packages folder with its JSON beside `houdini-ai-assistant-openai/`. Disable the old package, restart Houdini and launch the AI Assistant shelf. GitHub's automatic source ZIP has no runtime and is not the artist installer. See [README installation](../README.md#install-without-a-terminal).

## Validation completed

Validation used isolated processes and disposable scenes, not the artist's open scene. No paid OpenAI model requests or new Uthana generations were made.

| Check | Result |
|---|---|
| Offline unit suite | 71 tests: 70 passed, one symlink-permission skip |
| Windows junction escape test | Passed separately within that suite |
| Native Codex | Bundled executable initialized in a private empty profile; no account read/login/model turn |
| Setup UI | Consent, masked key, retry, cancellation, remembered backend and launch behavior passed |
| Scene chats | First Save, Save As, reopen, per-file history, unsent draft and untitled discard passed |
| Checked tools | Native geometry and tuple edits passed; Python/file nodes, modified expressions, callbacks and outside outputs rejected |
| SDK/panel bridge | Geometry, duplicate calls, Stop and scene-change guards passed without a live model |
| APEX | Factory-rig discovery, keys, interpolation, layer preservation, invalid-batch rejection and focus regressions passed |
| Uthana | Existing cached FBX imported/retargeted locally; 442 keyed channels, 299 varying; output reinspection passed |
| Solaris | SOP import, MaterialX binding, lights, camera and Karma settings passed |
| Rendering | Completed XPU render; a separate run returned WIP before completion and was cancelled; API worker returned actual image content without an API call |
| Release audit | Source syntax/paths/links, PowerShell syntax, staged source and full Git history secret scans passed |
| Clean extraction | Contents/hashes/signatures, relocated imports, offline setup, native package/shelf discovery, consent UI, per-scene chat and checked geometry passed |

Local evidence is in `.local/checks/`, including `validation-package-060.json`, `unit-060.txt`, redacted Gitleaks reports and native validation reports. These reports are intentionally not committed because they can contain workstation paths. Tests can overwrite their own reports; the table also records the successful WIP/cancel run separately from the final completed-render run.

The Houdini license issue was fixed by the owner before native checks completed. An existing external OCIO configuration produced host warnings; spawned workers now use their private preferences, and the final clean-profile package check passed without that warning. Do not change the artist's color configuration as part of publishing.

## Reproduction and next steps

Use the full commands and prerequisites in [Development](DEVELOPMENT.md). Key commands from the repository root:

```powershell
# Explicit developer downloads, not end-user setup:
./setup.ps1 -PythonExe 'C:/path/to/Python313/python.exe' -DownloadDependencies
& ./.venv/Scripts/python.exe scripts/build_runtime.py --download

# No account/model calls:
& ./.venv/Scripts/python.exe -m unittest discover -s tests/unit -t .
& ./.runtime/python/python.exe -m tests.integration.check_codex_idle

# The builder reads the staged Git index, not arbitrary working files:
& ./.venv/Scripts/python.exe scripts/audit_release.py
& ./.venv/Scripts/python.exe scripts/build_plugin.py
& ./.venv/Scripts/python.exe scripts/check_plugin.py dist/houdini-ai-assistant-0.6.0.zip
```

Stage reviewed source before the last three commands and run a separate redacting secret scan of staged changes/history. The runtime builder intentionally refuses to mix into an already completed bundle; use a fresh build checkout for dependency changes. A Linux VPS can store/review/push the source, but cannot validate Windows DPAPI, the Windows installer or native Houdini/Qt behavior.

Remaining work before treating this candidate as a stable public installer:

1. Have a second Windows user install the complete ZIP and perform fresh subscription/API sign-in with their own account. This was not replaced by simulated login tests.
2. Confirm focus in a real docked Houdini pane and review supported animation visually. Headless/native tests do not cover every workstation's window behavior.
3. Expand custom-node/rig support only through audited checked adapters and meaningful denial tests. Never reintroduce unrestricted execution to make a scene work.
4. Keep the published installer marked as a pre-release until the remaining sign-in checks pass. Future rebuilt ZIPs/checksums must be audited and attached as release assets, never added to Git.
5. Keep remote source hashes aligned and record any future installer rebuild's source revision, test scope and checksum.
