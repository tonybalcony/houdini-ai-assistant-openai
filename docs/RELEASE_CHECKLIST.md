# Release review — 0.6.0 candidate

The owner requested the contained installer and explicitly chose checked tools over unrestricted execution. On 2026-09-30 the owner authorized pushing source and the [handover](HANDOVER.md) to GitHub and the VPS. After the owner asked how others could install the plugin, the tested ZIP/checksum were published as [pre-release v0.6.0-rc.1](https://github.com/tonybalcony/houdini-ai-assistant-openai/releases/tag/v0.6.0-rc.1), targeting implementation commit `8782076`. GitHub's uploaded-asset digest matches the tested local ZIP; the stable-release sign-in checks remain pending.

- [x] Remove texture tools and upstream unrestricted MCP/RPyC integration.
- [x] Bundle portable Python/Codex/libraries; no first-run downloads or OS installer.
- [x] Add explicit setup consent and document every assistant storage location.
- [x] Isolate account state inside the plugin; no global sign-in/history migration.
- [x] Per-saved-scene chats; untitled chats in memory; project-local render/motion caches.
- [x] Enforce direct path and checked scene-operation boundaries; no bypass mode.
- [x] Offline suite: 71 tests completed: 70 passed and one Windows symlink-permission skip; separate Windows junction escape test passed. Native Codex initialized in an empty private test profile without account/model calls.
- [x] Staged source and full Git history credential scans: no findings. Index/source audit: no findings. Full ZIP content and runtime SHA-256 audit: passed; no private state included.
- [x] Native source tests: setup consent/retry/cancel, panel chat restore, first Save/Save As/load/untitled discard, checked edits and denial cases, SDK bridge and APEX/focus regressions.
- [x] Extracted full package: 3,973 runtime file hashes, Python/Codex signatures, relocated imports, offline setup, native package/shelf discovery, consent UI, scene chat and checked geometry. No sign-in/model request performed.
- [ ] Test new human subscription/API sign-in on a separate Windows installation.
- [x] Native Houdini 22.0.368: factory Electra APEX keys; cached Uthana import/retarget (442 keyed/299 varying channels) and safe output reinspection; Solaris/MaterialX/lights/camera; completed Karma XPU render; WIP image available before completion and cancellation; API worker image bridge without API calls.
- [x] Publish the complete installer for users to try, with explicit pre-release labeling, install instructions and a verified checksum. Keep binaries out of Git.

Validation resumed on 2026-09-30 after the owner fixed the Houdini license. Native tests above now pass. Houdini's existing external OCIO setting reports a missing configuration in the host; spawned render workers no longer inherit that external setting and use versioned preferences inside the plugin. Windows render-state publication retries brief reader locks instead of aborting the render. These checks do not validate every custom rig, live docked-pane focus on another PC or fresh online sign-in with a second person's account. No paid model requests or new Uthana generations were made for this refactor.

Source remains MIT and text-only. The full artist ZIP adds `.runtime` under its source folder. No `.state`, accounts, scenes, chat history, caches, downloaded user assets or maintainer machine settings may enter the ZIP.
