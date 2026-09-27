# Development and validation

Run commands from the repository root in PowerShell. This is loaded Python source, not a compiled app. Keep SDK dependencies outside Houdini's embedded interpreter.

## Setup and configuration

Normal users install the plugin ZIP and use its first-run Qt setup window; see the
README. Developers can still prepare the same dependencies from PowerShell:

```powershell
./setup.ps1 -PythonExe 'C:/path/to/signed/Python313/python.exe'
```

Full setup installs both environments. `setup_mcp.ps1` installs only MCP/helpers. Both use `setup_common.ps1`, require signed 64-bit Python 3.13, and check native command failures.

- `requirements.txt`: direct API dependencies.
- `requirements-lock.txt`: complete worker environment, used by setup.
- `requirements-mcp-lock.txt`: complete MCP/helper environment.
- `install_mcp_source.py`: verifies upstream revision/archive hash before extraction.
- `vendor/`: ignored download. Existing source is reused; use a clean checkout for a fresh dependency check.
- `panel_install.py`: generates ignored `.local/astra.pypanel` from a portable template.
- `bootstrap.py`: stdlib-only background installer, signed runtime downloads and a
  dependency fingerprint in `.local/setup.json`. A process lease prevents parallel installs.
- `setup_ui.py`, `launch_ui.py`, `account_worker.py`: first-run UI, shelf entry and
  private-pipe authentication. Houdini's Qt thread never runs network/login calls.
- `user_account.py`: per-user preferences and Windows DPAPI key protection.
- `codex_paths.py`: shared discovery including a verified local Codex fallback.

Version pins are not artifact hash locks. Setup needs package-index and GitHub access. Upstream wheels/build files are generated locally and not committed.

| Setting | Use |
|---|---|
| `HOUDINI_ASTRA_CODEX` | Explicit Codex executable; otherwise PATH, desktop runtime, then `.local/codex`. |
| `HOUDINI_ASTRA_PYTHON` | Prepared assistant/Uthana interpreter; does not override MCP/helper interpreter. |
| `OPENAI_API_KEY` | Legacy API key from process or Windows environment; a key saved through setup takes precedence. |
| `HOUDINI_ASTRA_USER_DIR` | Override account preference/DPAPI storage, especially for isolated dummy-key tests. |
| `UTHANA_API_KEY` | Optional Uthana helper key override. |
| `HOUDINI_ASTRA_TEXTURE_LIBRARY` | Texture folder, before `local_settings.json`; absent means cache-only. |
| `HOUDINI_ASTRA_CHAT_DIR`, `HOUDINI_ASTRA_LOG_DIR` | Alternate chat/log folders. |
| `HOUDINI_ASTRA_HYTHON` | Test-only full hython path. |
| `HOUDINI_ASTRA_MODEL`, `HOUDINI_ASTRA_CHAT_ID`, `HOUDINI_ASTRA_LOG_SESSION`, `HOUDINI_ASTRA_MCP_PORT` | Internal per-connection values supplied by the panel. |

Copy `local_settings.example.json` for a texture folder. Never put credentials in local settings. Restart/reopen after configuration changes; running processes can retain earlier values. The README explains independent user sign-in.

## Offline regression

```powershell
& ./.venv/Scripts/python.exe -m unittest test_worker test_codex_worker test_uthana test_mcp test_models test_chat_history test_diagnostics test_packaging test_onboarding
& ./.mcp-venv/Scripts/python.exe -m unittest test_texture_tools
```

No model calls, Houdini license or external credentials. Onboarding tests use dummy
keys in temporary folders. The DPAPI check needs a normal Windows user profile;
a restricted execution sandbox may not provide one. Do not replace encryption
with plaintext to make a sandbox test pass. Run individual modules for narrow changes.
Avoid recursive discovery into downloaded vendor tests.

## Native checks without model calls

Use disposable hython processes, never the artist's open scene:

```powershell
$hython = 'C:/path/to/Houdini/bin/hython.exe'
$env:HOUDINI_ASTRA_HYTHON = $hython
$env:QT_QPA_PLATFORM = 'offscreen'
& $hython check_chat_panel.py
& $hython check_onboarding.py
& $hython check_sdk_assistant.py
& $hython check_apex_assistant.py
& $hython check_solaris.py
& ./.venv/Scripts/python.exe check_mcp.py --solaris
```

`check_support.py` discovers hython from an explicit override, PATH, HFS or a single installed Houdini 22 folder. Multiple ambiguous installations require an override. Panel checks use temporary chat stores.

The MCP check requires Codex ChatGPT sign-in and Houdini licensing. It performs native scene operations without a model turn. Raw stderr goes to `.local/mcp_check_stderr.log`. Lookdev checks create synthetic maps in the ignored cache; no private texture library or licensed asset is needed.

`check_onboarding.py` runs the actual Qt setup widgets with mocked installation and
auth events: retry, cancellation, masked key entry, remembered backend and launch
behavior. It writes only a setup preview image into `.local/`. It does not sign in,
log out or use a real API key. With `HOUDINI_ASTRA_CHECK_PACKAGE=1`, it additionally
asserts native package/shelf registration; run from an extracted plugin with
`HOUDINI_PACKAGE_DIR` pointing to its parent directory. Use an isolated
`HOUDINI_USER_PREF_DIR` containing the required `__HVER__` placeholder for native tests.

### Optional renders

```powershell
& $hython check_solaris.py --render
& $hython check_solaris.py --render --wip
& ./.venv/Scripts/python.exe check_asset_bridge.py
& ./.venv/Scripts/python.exe check_mcp.py --solaris
```

Real XPU compute/licensing, no model calls. The asset bridge needs a preview-producing job recorded in `validation-solaris-render.json`. The MCP image assertion runs when that report exists; otherwise the report explicitly says skipped. A pass without it does not verify image delivery. The WIP check reports whether an image arrived before completion; fast renders may finish first.

For optional cached motion retargeting:
```powershell
& $hython check_uthana_assistant.py '<already-downloaded-asset-id>'
```
Supply your own cache entry. No new generation is performed. A uniquely named example is written to ignored `output/`; no motion fixture is distributed.

### Live tests: cost-bearing

| Command | Behavior |
|---|---|
| `& ./.venv/Scripts/python.exe check_mcp.py --live` | One subscription turn. |
| `& $hython check_sdk_assistant.py --live --subscription` | Two subscription turns through the panel. |
| `& $hython check_sdk_assistant.py --live` | Two paid API turns. |
| `& ./.venv/Scripts/python.exe check_chat_restart.py` | Two Terra subscription turns even without a --live flag. |

`check_assistant.py` delegates to the SDK check. The MCP host and restart Houdini scripts are child-process helpers. Do not invoke all check scripts indiscriminately.

## Troubleshooting

1. Read the current session in `.logs/`; correlate run/call IDs without dumping private history.
2. If the worker cannot start, inspect its recorded program/OS error, run both environment interpreters with `--version` and inspect `Get-AuthenticodeSignature`. An unsigned Houdini launcher previously failed Smart App Control.
3. Use signed standalone Python. To repair a same-major/minor environment after a base-runtime change, back up configuration and use Python's `-m venv --upgrade --without-pip`, then `pip check`. Setup does not relocate existing environments. Do not weaken security policy.
4. If readiness fails, check Codex login, executable discovery, package compatibility, listener port and `check_mcp.py`.
5. A timeout may leave completed edits. Inspect scene/job state before retrying. Stop cannot forcibly abort every HOM cook.
6. Render diagnostics live in `.render_jobs/<id>/state.json`; keep XPU and report device initialization errors.
7. API keys/model access and Codex subscription sign-in are separate. No billing fallback exists.
8. First-run problems: use **Open setup log**, fix the reported dependency/network
   issue, then **Retry**. The normal Windows PowerShell signature check uses system
   modules so inherited PowerShell 7 module paths cannot break verification.
9. **Account** reopens setup. Clearing only `preferences.json` in the user data
   folder resets onboarding; do not delete Codex auth/session files or saved chats
   as a troubleshooting shortcut. A corrupt encrypted API key must be re-entered.

Only stop test-owned processes. Do not clear user chats, delete referenced caches or change global Codex settings to pass a check.

## Release validation

Build the installable archive after staging the exact intended source:

```powershell
& ./.venv/Scripts/python.exe scripts/build_plugin.py
```

The builder audits and reads the **Git index**, not untracked/ignored files, and
produces ignored `dist/houdini-ai-assistant-<VERSION>.zip`. Its root contains
`houdini-ai-assistant.json` alongside `houdini-ai-assistant-openai/`. Houdini does
not automatically scan arbitrary nested folders for package JSON. Never include
prepared environments, downloaded runtimes, account data or caches in the ZIP.

Extract the archive into a fresh writable test folder, run first setup, check both
environments with `pip check`, and validate native shelf registration. The no-Python
path uses the signed Python installer with a per-user target; setup must never
disable execution policy or Smart App Control. An existing supported signed Python
can be reused. Test account changes only with disposable state or explicit consent;
reading existing ChatGPT sign-in through App Server does not require changing it.

Windows CI runs offline tests and source hygiene, not native Houdini, sign-in or rendering. Before releasing, install a new clone with fresh environments and no private settings/history, then run available native checks.

Audit the Git index/history with `scripts/audit_release.py` and a credential scanner such as Gitleaks with redaction. Review raw logs/reports before sharing. Historical validation files are not evidence for new changes.

`VERSION` supplies the App Server client version. Update it and the changelog together. Publication/tags are separate from local commits.
