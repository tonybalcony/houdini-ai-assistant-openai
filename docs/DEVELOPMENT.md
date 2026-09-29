# Development and validation — 0.6.0

Work from the repository root. Windows x64/Python 3.13 is the build target; Houdini 22.0.368 is the native development host. The model backend is external to Houdini; never install SDKs into Houdini's embedded Python.

## Developer setup and build

Artist installs use the complete plugin ZIP and offline setup UI. A source checkout has no runtime binaries. Maintainers explicitly opt into downloads:

```powershell
./setup.ps1 -PythonExe 'C:/path/to/Python313/python.exe' -DownloadDependencies
& ./.venv/Scripts/python.exe scripts/build_runtime.py --download
```

The first command creates only the development environment. The second downloads verified official portable Python/Codex archives and exact-version wheels into `.local/build-downloads`, then assembles `.runtime`. It checks publisher signatures and retains license notices. Houdini child preferences use `.state/houdini__HVER__` (the version token is required by Houdini). Rebuild changed dependencies from a fresh checkout rather than mixing old runtime contents.

Stage intended source before auditing/building; the package builder reads the Git index:

```powershell
& ./.venv/Scripts/python.exe scripts/audit_release.py
& ./.venv/Scripts/python.exe scripts/build_plugin.py
& ./.venv/Scripts/python.exe scripts/check_plugin.py dist/houdini-ai-assistant-0.6.0.zip
```

The ZIP includes audited source plus manifest-listed runtime files. `.state`, `.local`, secrets, user chats/caches, test outputs and sibling workspace files are excluded. Runtime binaries belong only to the ZIP, never Git. The dependency manifest must match the staged lockfile. Scan the staged source and history separately with a redacting credential scanner.

## Offline tests

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s tests/unit -t .
```

Repeat against `.runtime/python/python.exe` to verify the actual distribution. Tests use dummy credentials and disposable directories; they do not make model calls. DPAPI tests need a normal Windows user profile; sandbox-created users may not support it. Symlink tests report a skip when Windows does not grant symlink creation; also test junction escapes on a normal workstation.

Important coverage: outside paths and aliases, private directories, device names, unsaved memory-only chats, separate saved-scene histories, consent before setup, corrupt manifests, ephemeral subscription threads, historical context without replay, unknown tools, exact model/billing separation and API checkpoints.

## Native checks

Run disposable processes only, never the artist's open scene:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$hython='C:/path/to/Houdini/bin/hython.exe'
& $hython -m tests.integration.check_onboarding
& $hython -m tests.integration.check_chat_panel
& $hython -m tests.integration.check_scene_scope
& $hython -m tests.integration.check_scene_policy
& $hython -m tests.integration.check_sdk_assistant
& $hython -m tests.integration.check_apex_assistant
& $hython -m tests.integration.check_solaris
& ./.runtime/python/python.exe -m tests.integration.check_codex_idle
```

The Codex check only initializes the bundled App Server in a disposable profile; it does not log in or request a model response. Houdini checks require a current license. `check_solaris --render` uses real Karma compute; it writes disposable test artifacts into `.local/checks` and its saved test scene's `.astra` directory. `check_asset_bridge` additionally needs that render report and the test scene supplied as `HOUDINI_ASTRA_SCENE`.

`check_sdk_assistant --live --subscription` consumes subscription usage; `--live` without `--subscription` makes paid API calls. Do not run live checks for packaging without explicit authorization. `check_uthana_assistant <asset-id> <existing-cache-root>` copies an existing cached asset into a disposable saved scene; it performs no Uthana API calls. Never generate paid motion merely to test a refactor.

## Runtime rules

- No ambient executable, global chat-directory, global Codex profile or global API-key lookup. Runtime programs come from `.runtime`.
- The panel supplies `HOUDINI_ASTRA_SCENE`; children use that same saved-scene scope. It is not a model-settable option.
- `.state/codex` is plugin-owned authentication storage; do not inspect/copy it while developing or packaging.
- `UTHANA_API_KEY` or the ignored plugin-local `.secrets/uthana_api_key` is optional. Keys never enter model messages.
- No automatic migration of old `.chat_history`, global user preferences or texture libraries. Do not delete old user data.
- Extend the checked tool contracts and path/cook policy together. Unsupported operations fail with Access denied. Do not add an unrestricted override to solve a regression.

Reports/screenshots go under `.local/checks`. Documentation-only changes do not require model or render calls. Record native checks that could not run; older validation reports are not evidence for a changed release.
