# Coding-agent guide — 0.6.0

This repository is a Windows Houdini panel plus portable local workers. Read [Architecture](docs/ARCHITECTURE.md), [Development](docs/DEVELOPMENT.md), [Security](SECURITY.md) and [Release checklist](docs/RELEASE_CHECKLIST.md). The [0.6.0 handover](docs/HANDOVER.md) records the implementation, evidence and remaining work.

## Decisions to preserve

- The owner explicitly chose folder restriction over unrestricted tools on 2026-09-29. No arbitrary Python, shell, VEX snippets, upstream MCP/RPyC server, external apps or permission-bypass mode. A user-provided outside path is still denied.
- Assistant data stays in this installed plugin or the current saved `$HIP`. `access_policy.py` resolves paths, rejects escapes/private state and sets child temp/profile roots. `scene_policy.py` checks node types, factory definitions, parameters and cooks. Unknown/unsafe operations fail closed. Houdini/Windows runtime files are a necessary host dependency, not a promise of an OS sandbox.
- Generic code execution was deliberately removed. Do not restore it to make a rig or node work. Custom/unlocked HDAs and unverified APEX rigs are unsupported; report that limitation.
- Texture search/download/generation/binding and external texture-library configuration are removed. Keep old user caches untouched.
- Subscription uses a separate plugin-local Codex profile and ephemeral threads. API mode is explicit and separately billed. Preserve exact model IDs, no automatic fallback, no automatic request replay.
- Chats belong to one saved scene filename. Unsaved scenes use memory only. Save As switches stores; no cross-scene global chat list. Subscription reconnect restores bounded visible history as context, not a native hidden rollout. API checkpoints preserve model items.
- `.runtime` is a portable verified distribution; `.state` is private installation/account/log/temp state. No first-launch downloads, pip, registry edits or system installers. The setup plan requires explicit unchecked consent. Developer downloads require explicit build flags.
- Keep credentials out of source, model context, logs and test data. Do not inspect `.state/codex`, `.state/account` or `.secrets` for maintenance. API keys use DPAPI; native Codex owns its private file-store sign-in.
- Keep `hou` on Houdini's main thread and SDK/network work outside it. Private pipes carry versioned JSON only; diagnostics go to the logger.
- Preserve run/call IDs, duplicate-call handling, scene-generation guards, Stop and undo groups. A timeout may have applied edits; inspect before retrying.
- Render in Solaris using Karma XPU; lights in Solaris, materials in MaterialX. Prefer bounded working renders/WIP previews. Never silently switch render engine.
- Uthana receives only motion text/settings. Download into the saved scene's cache; no uploads of rigs/assets/scenes. Preserve submission idempotency and uncertain-result recovery.

## Work and validation

Run `python -m unittest discover -s tests/unit -t .` with the development or bundled interpreter. Use dummy-key/profile overrides in tests, never real account changes. Native modules are listed in the development guide; some require a license or paid model access. Do not run every integration check indiscriminately. Reports belong to ignored `.local/checks`.

Runtime modules intentionally remain at the root for Houdini import compatibility. Add source checks/tests in their existing folders. Source in Git stays text-only. The release ZIP includes manifest-verified `.runtime` files explicitly; never broadly archive a used plugin directory. Stage intended source, run `scripts/audit_release.py` plus a separate redacted credential/history scan, then `scripts/build_plugin.py`. Preserve third-party notices. Version and changelog move together.

Keep the existing `vps` and GitHub `origin` remotes distinct. The owner authorized pushing the 0.6.0 source and handover to both existing remotes on 2026-09-30. The installer was subsequently published on GitHub as pre-release `v0.6.0-rc.1` on 2026-09-30, targeting implementation commit `8782076`. The verified ZIP/checksum are release assets, never Git source; record future release/tag operations explicitly. Do not change the artist's open scene or delete old chats/caches as part of this refactor. Keep sibling scenes, backups and renders out of Git.
