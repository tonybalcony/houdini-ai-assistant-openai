# Development and validation

Run commands from the repository root in PowerShell. This is loaded Python source, not a compiled app. Keep SDK dependencies outside Houdini's embedded interpreter.

## Setup and configuration

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

Version pins are not artifact hash locks. Setup needs package-index and GitHub access. Upstream wheels/build files are generated locally and not committed.

| Setting | Use |
|---|---|
| `HOUDINI_ASTRA_CODEX` | Explicit Codex executable; otherwise PATH then desktop runtime discovery. |
| `HOUDINI_ASTRA_PYTHON` | Prepared assistant/Uthana interpreter; does not override MCP/helper interpreter. |
| `OPENAI_API_KEY` | Explicit API mode, from process or Windows user/machine environment. |
| `UTHANA_API_KEY` | Optional Uthana helper key override. |
| `HOUDINI_ASTRA_TEXTURE_LIBRARY` | Texture folder, before `local_settings.json`; absent means cache-only. |
| `HOUDINI_ASTRA_CHAT_DIR`, `HOUDINI_ASTRA_LOG_DIR` | Alternate chat/log folders. |
| `HOUDINI_ASTRA_HYTHON` | Test-only full hython path. |
| `HOUDINI_ASTRA_MODEL`, `HOUDINI_ASTRA_CHAT_ID`, `HOUDINI_ASTRA_LOG_SESSION`, `HOUDINI_ASTRA_MCP_PORT` | Internal per-connection values supplied by the panel. |

Copy `local_settings.example.json` for a texture folder. Never put credentials in local settings. Restart/reopen after configuration changes; running processes can retain earlier values. The README explains independent user sign-in.

## Offline regression

```powershell
& ./.venv/Scripts/python.exe -m unittest test_worker test_codex_worker test_uthana test_mcp test_models test_chat_history test_diagnostics test_packaging
& ./.mcp-venv/Scripts/python.exe -m unittest test_texture_tools
```

No model calls, Houdini license or external credentials. Run individual modules for narrow changes. Avoid recursive discovery into downloaded vendor tests.

## Native checks without model calls

Use disposable hython processes, never the artist's open scene:

```powershell
$hython = 'C:/path/to/Houdini/bin/hython.exe'
$env:HOUDINI_ASTRA_HYTHON = $hython
$env:QT_QPA_PLATFORM = 'offscreen'
& $hython check_chat_panel.py
& $hython check_sdk_assistant.py
& $hython check_apex_assistant.py
& $hython check_solaris.py
& ./.venv/Scripts/python.exe check_mcp.py --solaris
```

`check_support.py` discovers hython from an explicit override, PATH, HFS or a single installed Houdini 22 folder. Multiple ambiguous installations require an override. Panel checks use temporary chat stores.

The MCP check requires Codex ChatGPT sign-in and Houdini licensing. It performs native scene operations without a model turn. Raw stderr goes to `.local/mcp_check_stderr.log`. Lookdev checks create synthetic maps in the ignored cache; no private texture library or licensed asset is needed.

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

Only stop test-owned processes. Do not clear user chats, delete referenced caches or change global Codex settings to pass a check.

## Release validation

Windows CI runs offline tests and source hygiene, not native Houdini, sign-in or rendering. Before releasing, install a new clone with fresh environments and no private settings/history, then run available native checks.

Audit the Git index/history with `scripts/audit_release.py` and a credential scanner such as Gitleaks with redaction. Review raw logs/reports before sharing. Historical validation files are not evidence for new changes.

`VERSION` supplies the App Server client version. Update it and the changelog together. Publication/tags are separate from local commits.
