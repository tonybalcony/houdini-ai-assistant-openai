# Development checks

Run from the repository root. These files are versioned source, but are not included
in the plugin ZIP installed by artists.

| Directory | Purpose | Requirements |
|---|---|---|
| `unit/` | Worker, chat, protocol, credential and packaging tests | Assistant `.venv`; dummy credentials only |
| `textures/` | Offline texture IO/download validation | `.mcp-venv` with Pillow |
| `integration/` | Explicit Houdini, Qt, MCP, render and optional live checks | Licensed Houdini; some checks use accounts or billable turns |
| `support.py` | Portable host discovery and synthetic fixtures | Shared by selected checks |

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s tests/unit -t .
& ./.mcp-venv/Scripts/python.exe -m unittest discover -s tests/textures -t .
```

Run native checks as modules, for example `hython -m tests.integration.check_onboarding`.
Do not discover or import integration modules indiscriminately: they execute checks
when loaded. In particular, `check_chat_restart` makes subscription model calls.
See [the development guide](../docs/DEVELOPMENT.md) for exact commands and costs.

Reports and screenshots go into ignored `.local/checks/`; setup previews/logs use
`.local/`. Older local reports are preserved under `.local/archive/0.5.0-reports/`
and are not current test evidence.
