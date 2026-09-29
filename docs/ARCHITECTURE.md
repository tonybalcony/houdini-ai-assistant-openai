# Architecture — 0.6.0

## Execution

The Houdini Qt panel owns a separate portable Python worker through versioned JSON-line messages on private process pipes. `hou` runs only on the Houdini main thread. Network/SDK work stays outside the embedded interpreter.

Subscription: `astra_panel.py` → `codex_worker.py` → bundled Codex App Server → selected model. API: panel → `worker.py` → Agents SDK/Responses API. Billing modes and exact model IDs stay separate. All scene functions return through the same panel run/call/scene-generation guards. There is no upstream MCP process, RPyC listener or arbitrary code tool.

## Module map

| Modules | Responsibility |
|---|---|
| `launch_ui.py`, `open_panel.py`, `panel_install.py`, `astra.pypanel`, `toolbar/astra.shelf` | Shelf entry, onboarding decision, generated registration, Qt panel loading |
| `setup_ui.py`, `bootstrap.py` | Explicit setup plan/consent; offline manifest, signature and import verification |
| `account_worker.py`, `user_account.py`, `codex_paths.py`, `codex_policy.py` | Plugin-local authentication and fixed portable Codex; no global executable/profile discovery |
| `access_policy.py`, `scene_policy.py` | Saved-HIP scope, resolved file containment, child environment, checked native node/parameter/cook policy |
| `astra_panel.py`, `scene_tools.py`, `tool_contracts.py` | UI, saved chats, scene dispatch, schemas, mutation guards and undo |
| `codex_worker.py`, `worker.py` | Subscription/API protocols, streaming, rate limits, cancellation and context restoration |
| `apex_tools.py`, `uthana_scene.py` | Dedicated local animation/retargeting; reject unverified rig graphs |
| `uthana_client.py`, `uthana_worker.py`, `uthana_qt.py` | Optional text-only motion service, quota/idempotency and project-scoped cache |
| `solaris_contracts.py`, `solaris_tools.py`, `workflow_policy.py` | Solaris, MaterialX, Karma XPU and render conventions |
| `render_jobs.py`, `render_job_worker.py`, `asset_worker.py` | Saved-scene render jobs, private snapshots, previews and cancellation |
| `chat_store.py`, `diagnostics.py` | Per-scene SQLite or in-memory chats; private bounded logs |
| `scripts/build_runtime.py`, `scripts/build_plugin.py`, `scripts/audit_release.py` | Maintainer-only downloads, verified runtime manifest, audited index-based ZIP assembly |

## Persistence

`ChatStore()` derives its directory from the current saved scene, never from a global chat-directory environment override. Each filename maps to its own `$HIP/.astra/<scene-id>`. Without a saved scene it uses SQLite in memory. Explicit directory injection is for disposable tests only. Writer leases are OS-released locks for persistent chats. A scene change stops the old connection and switches the store; Save As does not leak another file's chats. A first save retains visible transient text, then reconnects separately.

Codex threads are always ephemeral. Reconnection starts a new ephemeral thread and includes at most 80,000 characters of saved visible conversation as untrusted historical context on the first user turn. There is no hidden native history/resume guarantee. API mode persists serialized conversation items/checkpoints. Neither mode automatically replays interrupted requests.

Accounts, setup marker, private Codex profile, logs and process temp files are under `.state` in the plugin. The API key uses Windows DPAPI. Codex manages its native file-store sign-in; do not read it into the model or copy it into project history.

## Bundle

The public Git source stays text-only. The artist ZIP additionally contains an ignored `.runtime` directory built from official, pinned Python/Codex archives and exact-version wheels. Python is the embeddable distribution, not a Windows installer or relocated venv. Its `_pth` file uses relative paths. Package licenses and Codex notices remain with the bundle; pip CLI launchers and local-origin metadata are omitted. `manifest.json` records file hashes and input artifact hashes.

Bootstrap has no network download path. It asks for consent, verifies files/publishers/imports, then launches authentication. The separate maintainer builder requires `--download`. Missing runtime files fail closed.

## Boundaries and limitations

Use resolved folder checks at every file-capable tool boundary, not merely in prompts. Private state and executable parameters are never ordinary scene assets. The generic node allowlist is intentionally conservative. Custom/unlocked HDAs, script-bearing graphs and unverified APEX rigs are unsupported. Exact native template computations are accepted only for specific audited fields; other expressions are denied. Generated MaterialX builder inheritance settings are frozen to literals. Uthana bakes copy only animation data to a separate Scene Animate on the original verified rig chain; later edits never require trusting the procedural retarget branch. No runtime path override or user prompt may enable arbitrary execution.

The policy does not sandbox Houdini itself, trusted factory implementations, OS libraries or hostile external processes. See [Security](../SECURITY.md). Native cooks can block the UI; undo groups are per batch and failures can leave partial edits. A timeout never proves an operation did not happen. Uthana submissions with an uncertain result are not automatically repeated.
