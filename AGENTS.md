# Guide for coding agents

This is a Windows Houdini Python Panel application distributed as a source-only
Houdini package archive, not a web service. Commands below assume this directory is the working
directory. Tested host: Houdini 22.0.368, PySide6, Python 3.13.

Read [ARCHITECTURE.md](ARCHITECTURE.md) for module ownership and process boundaries,
[DEVELOPMENT.md](DEVELOPMENT.md) for setup/tests, and
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before preparing a public repository.
`README.md` is the public user guide. Historical local lessons/reports are excluded
from Git; they are not current implementation specifications.

## Preserve these decisions

- Default to Codex App Server with ChatGPT sign-in. The Agents SDK API worker is
  a separate, explicit, paid backend. Never introduce automatic backend/model
  fallback. Exact model IDs and tool schemas live in `tool_contracts.py`.
- Keep cloud requests and SDK dependencies outside Houdini's embedded Python.
  Execute `hou` scene operations on Houdini's main thread. Background rendering
  and asset/network helpers have separate processes.
- Keep panel/worker stdout as newline-delimited JSON only. Put diagnostics in the
  existing logger; do not print debug messages into protocol streams.
- Preserve run/call IDs, duplicate-call handling, scene-generation guards and Stop
  behavior. A timed-out mutation may have applied: inspect before retrying.
  Undo groups are per batch, not atomic whole-turn rollback.
- Preserve saved chats and drafts. Use temporary `ChatStore` instances or
  `HOUDINI_ASTRA_CHAT_DIR` for tests. Reconnect must not silently replace a failed
  resume with an empty thread, replay interrupted requests or generate paid motion.
- Keep MCP scoped to this panel: loopback `127.0.0.1`, ephemeral port, stdio server,
  per-thread Codex configuration. Do not edit global Codex/Houdini startup settings.
  Keep upstream normal execution policy and disabled legacy tools in place.
- Render in Solaris with Karma XPU; light in Solaris; use MaterialX. Prefer working
  renders and inspect actual WIP images. Do not switch to Mantra or Karma CPU on
  failure. Working optimizations belong to exported snapshots, not original nodes.
- Uthana receives only motion text/settings using its built-in character. Never
  upload user rigs, geometry, scenes, images or video. Retarget locally. Preserve
  cache/idempotency and uncertain-submission recovery before another paid request.
- Keep credentials out of model context, logs, tests, source and commits. Do not
  read `.secrets/` for routine maintenance. Local textures are read from configured
  libraries; generated/downloaded textures go to the bounded project cache.
- Use a signed standalone Python runtime. The local `.python313` installation
  repaired Windows Smart App Control blocking during development; do not recreate
  environments from Houdini's unsigned Python or weaken Windows security.

## Change and validation workflow

1. Find the responsible module in the architecture map. Extend shared contracts
   and both backend routes when adding a tool. Solaris/texture tools use native
   MCP in Subscription mode and the dedicated/API path in API mode.
2. Prefer adapters in our code to edits under the pinned `vendor/` source. Its
   `AGENTS.md` describes the upstream project, not our maintainer workflow. If an
   upstream change is required, read its scoped guidance and record the patch and
   revision rather than silently replacing the vendor snapshot.
3. Run relevant offline tests first. Standard regression commands:

   ```powershell
   & ./.venv/Scripts/python.exe -m unittest test_worker test_codex_worker test_uthana test_mcp test_models test_chat_history test_diagnostics test_packaging
   & ./.venv/Scripts/python.exe -m unittest test_onboarding
   & ./.mcp-venv/Scripts/python.exe -m unittest test_texture_tools
   ```

4. Use disposable `hython` scenes for HOM/APEX/USD/Qt work. `check_mcp.py` tests
   real Codex/MCP connectivity without a model turn by default. Test prerequisites,
   fixtures, outputs and paid variants are listed in `DEVELOPMENT.md`.
5. Do not run every `check_*.py` indiscriminately. `check_chat_restart.py` makes
   subscription model calls even without `--live`; SDK `--live` without
   `--subscription` uses the paid API. Do not generate Uthana motion merely to test
   documentation or a local fix.
6. Close/reopen the panel after Python/UI changes; reconnecting alone does not reload
   the panel. Maintain dependency reload order in `astra.pypanel` where necessary.
   New dynamic tools may require a new chat; resume restores the old dynamic schema.
7. Update the relevant guide and report actual verification, including skipped
   machine-specific checks. Historical `validation-*.json` files are not proof that
   a new change passes. Documentation-only edits do not require model/render runs.

Do not change the user's open scene, remove caches used by scene files, publish,
push, choose a license or acquire paid assets unless the task calls for it.

## Public source and installation

- Repository root is this directory. Keep sibling scenes/backups outside Git.
- MIT was selected by the owner; preserve LICENSE and THIRD_PARTY.md.
- VERSION supplies the client release version. Keep changelog and installation docs current.
- Setup downloads the exact pinned MCP archive with checksum validation. The entire
  vendor tree and protocol reference dumps stay ignored; do not commit them.
- open_panel.py generates .local/astra.pypanel from the portable template. Never
  embed an installation path in tracked source. local_settings.json holds optional
  machine paths; only local_settings.example.json is public.
- Run scripts/audit_release.py on the Git index plus a separate credential scanner
  before release. Review generated files and staged paths; never force-add secrets.
- First-run setup is owned by launch_ui/setup_ui/bootstrap. Keep installation off
  Houdini's UI thread and login in account_worker; credentials travel through pipes,
  never argv or model context. Native Codex manages subscription auth; API keys use
  per-Windows-user DPAPI outside source. Never persist plaintext API keys.
- Account choices are explicit and remembered. Auto-connect must preserve a saved
  chat's backend/model and must not send a model request or replay pending inputs.
- scripts/build_plugin.py reads the audited index and VERSION. Stage intended
  changes before building. The ZIP must contain root package JSON beside the source
  folder; runtimes, vendor downloads and user settings remain excluded.
- Test onboarding with temporary HOUDINI_ASTRA_USER_DIR and dummy keys only.
  check_onboarding.py covers real Qt without network; package discovery checks
  need an extracted archive and isolated Houdini preferences. Restart Houdini after
  setup-module changes rather than reloading a live installer thread.
