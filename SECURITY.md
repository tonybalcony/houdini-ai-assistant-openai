# Security and privacy

## Enforced tool boundary

The model receives explicit Houdini functions through the panel dispatcher. There is no arbitrary Python/shell tool, upstream MCP/RPyC listener, external app integration or automatic tool installation. Subscription mode uses a private `CODEX_HOME`, ephemeral threads, no execution environments and disabled shell, browser, image-file, app, hook and memory features. Unknown tool calls are rejected.

`access_policy.py` resolves file paths before use. Explicit outside paths, traversal, network paths, aliases, Windows device paths and private account/chat directories are rejected with **Access denied**. Existing symlinks/junctions are resolved before containment checks. Prompt checks give early feedback; each file-capable tool must enforce its own boundary regardless of prompt text. Generated outputs require a saved scene and live under its `$HIP`.

`scene_policy.py` restricts native node types, factory definitions, parameters and cooks. Model-authored code/expressions, Python callbacks, custom or modified HDAs and unsupported graphs are rejected. A short allowlist accepts exact computations from trusted native type templates (for example camera unit conversion); spare or modified expressions do not inherit that exception. APEX evaluation currently accepts only supported factory rig chains; arbitrary custom rigs are not silently allowed. Solaris stage/render dependencies are checked before export/renderer launch. Do not add a bypass flag or silently broaden a denied operation.

These checks do not sandbox the whole Houdini process. Houdini, Windows and installed drivers/libraries necessarily use their system files. Already-running user callbacks, malicious HIP/HDA contents, compromised dependencies and another local process are outside this application's security boundary. Filesystem checks also cannot prevent a hostile local process racing a path replacement. Use trusted scenes and a per-user writable installation, not a shared untrusted plugin folder.

## Installation and storage

First-run setup has an unchecked consent box and an explicit plan. It verifies the local manifest and Python/Codex publisher signatures before starting the bundled runtime. It never downloads software or invokes pip/an OS installer. Missing/corrupt bundles stop setup. Developer download/build scripts require their own explicit command-line opt-in and are not included in artist installs.

All assistant-owned account/settings/log/temp state lives in the plugin folder. API keys entered in the UI are encrypted with Windows DPAPI. Native Codex sign-in uses its own file store inside `.state/codex`; that native file is not encrypted by this project. It is never included in model context, logs or release archives. Other applications' Codex profiles and the old global user-settings folder are not imported. Authentication travels through private pipes, never command-line key arguments.

Saved chats and generated assets live in `$HIP/.astra/<scene-id>/`. Unsaved chats are memory-only. Logs exclude prompts and tool payloads and redact credential-like errors, but paths and diagnostics can still be private. Do not share a used plugin folder, `.state`, `.astra`, raw logs or credentials in an issue.

## Network

The selected OpenAI backend receives prompts, relevant context and tool results. Subscription and paid API are explicit alternatives with no fallback. API sign-in validates a key using the models endpoint without a model turn and refuses redirects on the credential-bearing request. Browser login URLs use the account helper's HTTPS host allowlist.

Optional Uthana tools send motion descriptions/settings only, using the user's own key. They never upload rigs, scenes, images or geometry. Downloads contain generated skeleton motion and are saved to the active saved scene's cache. No texture downloader or Fab login remains.

## Reporting

Use private vulnerability reporting on GitHub if enabled; otherwise request a private contact channel without disclosing secrets publicly. This preview has no guaranteed response time. Dependency pinning and checksums are not a full vulnerability audit.
