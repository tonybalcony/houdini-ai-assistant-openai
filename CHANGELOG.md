# Changelog

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
