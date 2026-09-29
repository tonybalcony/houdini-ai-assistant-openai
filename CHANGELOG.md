# Changelog

## 0.6.0 — contained installation and scene chats (release candidate)

- Bundle portable signed Python 3.13.15, Codex 0.157.1 and pinned libraries in the plugin ZIP. First launch verifies local files after explicit consent; no pip, downloads, registry edits or system installation.
- Keep account settings, a separate Codex profile, logs and temporary files inside the plugin. Existing global sign-ins and settings are not imported.
- Save chats beside each saved scene in its own `$HIP/.astra/<scene-id>/` directory. Unsaved chats remain in memory. Save As starts a separate scene history.
- Use ephemeral subscription threads, restoring the saved visible conversation as historical context on the next explicit prompt. No hidden Codex conversation archive is persisted.
- Remove texture search, download, generation and binding tools, external texture-library configuration and the upstream Houdini MCP/RPyC server.
- Route both backends through checked Houdini tools. Disable arbitrary Python/shell execution, Codex file/browser/app tools and tool installation. Reject outside paths and unsupported node/cook operations with Access denied.
- Store motion and render files beside the saved scene. Require a saved scene before generating motion or starting a render. Preserve Solaris, MaterialX and Karma XPU conventions.
- Custom HDAs, script nodes and unverified APEX rigs are unsupported under this policy; no unrestricted override exists.

## 0.5.2 - saved-chat connection recovery (2026-09-27; VPS Git only)

- Do not save a Codex resume ID for an unused connection; save it before the first user turn.
- Explain missing Codex rollout/history separately from sign-in failures.
- Offer an explicit New chat & connect action while preserving the old transcript and draft.
- Never replay a prompt or silently replace a missing conversation.
- Add real Codex idle reconnect and native Qt recovery checks without model requests.

## 0.5.1 - repository cleanup (2026-09-27; VPS Git only)

- Group offline tests, texture tests and opt-in Houdini checks under `tests/`.
- Move architecture, development, lookdev and release guides into `docs/`.
- Keep new validation reports and screenshots under ignored `.local/checks/`; preserve older reports in `.local/archive/0.5.0-reports/`.
- Exclude tests, maintenance scripts and CI configuration from installable plugin ZIPs.
- Update test commands, subprocess entry points and documentation links for the new layout.
- Preserve runtime entry points, saved data and account behavior. No GitHub publication.

## 0.5.0 - plugin setup preview (prepared 2026-09-27; publication pending)

- Houdini package archive and built-in AI Assistant shelf launcher.
- First-run setup window installs isolated dependencies and, when needed, verified Python/Codex runtimes.
- Browser-based Codex ChatGPT sign-in and masked API-key entry with Windows user encryption.
- Remembered account choice, automatic later connections and an Account button for setup recovery.
- Setup progress, retry/cancellation, isolated installation checks and credential/auth protocol tests.

## 0.4.0 - first public preview (prepared 2026-09-27; publication pending)

Included:
- Houdini Qt chat, streaming, Stop/Undo and saved conversations.
- Explicit Codex subscription and Agents SDK API backends; Astra, Sol and Terra.
- Native scene/APEX tools, pinned MCP and local Uthana retargeting.
- Solaris lighting, MaterialX, Karma XPU working renders and image previews.
- Local textures, authorized downloads, procedural texture writing and diagnostics.

Release preparation:
- Portable generated panel and machine-local texture settings.
- Signed Python setup with separate locked worker/MCP environments.
- Checksum-verified upstream download without vendor caches/source in Git.
- Synthetic lookdev fixtures, Houdini discovery and isolated chat tests.
- MIT license, contributor/security guides and release hygiene checks.

Native compatibility is tested on Houdini 22.0.368 / Windows. See the README for limitations. Earlier 0.3.x builds were local prototypes, not public releases.
