# Houdini AI Assistant (OpenAI)

An independent community assistant inside Houdini. Chat with GPT-6 Astra, GPT-5.6 Sol or GPT-5.6 Terra to inspect and edit a scene through checked tools. Choose your own ChatGPT/Codex subscription or your own OpenAI API key. There is no automatic switch between billing modes.

**0.6.0 release candidate:** self-contained Windows installation, scene-specific chats and restricted file access. This is not an official OpenAI or SideFX product.

## Install without a terminal

1. Download the **full `houdini-ai-assistant-0.6.0.zip` plugin asset** from the release you are installing. GitHub's automatic **Source code** ZIP does not include the runtime. [Releases](https://github.com/tonybalcony/houdini-ai-assistant-openai/releases).
2. In Houdini choose **File > Install Package Archive...**, select the ZIP and install in your own writable Houdini packages folder. Alternatively extract the ZIP there, keeping the package JSON beside the `houdini-ai-assistant-openai` folder.
3. Restart Houdini, enable the **AI Assistant** shelf, then click **Open Assistant**.
4. Review the setup plan and tick its consent checkbox. The plugin verifies its bundled Python, Codex and libraries. **It does not download dependencies, run pip, install Python system-wide, edit the registry or change PATH.**
5. Choose **ChatGPT subscription** and sign in in your browser, or **API key** and enter your own key. The plugin remembers this choice. API usage is billed separately.

Required: Windows x64, Houdini 22 (development host: 22.0.368), a valid Houdini license, internet access for the selected AI service, and account access to the selected model. Rendering requires a compatible Karma XPU setup. Optional Uthana generation requires separate Uthana access/credits.

The ZIP is larger than 0.5.x because it includes portable Python 3.13.15, Codex 0.157.1 and 40 pinned Python distributions. Nothing downloads during setup. If bundled software is missing or corrupt, setup stops and asks you to reinstall the full ZIP; it does not silently fetch replacements.

## What it can do

- Inspect scene metadata and author supported native nodes through checked operations.
- Create Solaris lights/cameras, MaterialX materials and Karma XPU settings.
- Run bounded working renders, inspect a WIP preview and cancel render jobs.
- Use dedicated APEX animation tools on supported factory rigs.
- Optionally request text-only Uthana motion, download it beside the saved scene and retarget locally when the target rig can be verified. No rig, scene or mesh is uploaded to Uthana.

Texture search, texture downloads/generation/binding, arbitrary Python, VEX snippets, shell execution and the upstream Houdini MCP/RPyC server were removed in 0.6.0. There is no unrestricted override. Creating unknown/custom HDAs, evaluating script-bearing networks and retargeting arbitrary custom rigs may return **Access denied**. See [the tool and storage policy](SECURITY.md).

## Files and saved chats

The assistant's file operations are bounded to its installed plugin folder and the **current saved scene's `$HIP` folder**. Generated scene output belongs in `$HIP`. Private account/chat files and plugin code are not exposed as scene assets. An outside path is rejected even when supplied by the user. Relative scene filenames resolve against `$HIP`; external environment aliases, network paths and directory traversal are rejected.

| Location | Contents |
|---|---|
| `packages/houdini-ai-assistant-openai/.runtime/` | Bundled Python, Codex, libraries, original license notices and a SHA-256 manifest |
| `packages/houdini-ai-assistant-openai/.state/` | This plugin's account preferences, private Codex sign-in, DPAPI-protected API key, logs and temporary files |
| `packages/houdini-ai-assistant-openai/.state/astra.pypanel` | Generated panel registration for this installation |
| `$HIP/.astra/<scene-id>/chats.sqlite3` | Chats and drafts for this exact scene filename |
| `$HIP/.astra/<scene-id>/motion/` and `renders/` | Generated motion, render snapshots, job state and previews |

An untitled scene's chat stays in memory and is lost when the scene or panel closes. Saving it while the panel is open preserves its visible conversation. **Save As** opens a separate history for the new filename; the original file's chats remain with the original file. Two scenes in one directory do not share chats. Move the `.astra` directory with the project to retain history and generated files. Renaming only the scene does not rename its history.

Subscription conversations use ephemeral Codex threads. On reconnect, up to the latest 80,000 characters of that scene's saved visible conversation are supplied as historical context on the next explicit user prompt. Hidden model reasoning and the original native Codex thread are not restored. API mode retains its serialized conversation checkpoints. Pending requests are never replayed automatically.

## Privacy and limits

This version uses a separate plugin-local Codex profile, so you sign in once even if the desktop app is already signed in. It does not import global chats, keys or settings. Codex's native sign-in file is private but not encrypted by this plugin; the API key is protected with Windows DPAPI. Do not distribute a used installation folder. Only distribute a freshly built release ZIP.

Prompts, relevant scene context and tool results go to the selected OpenAI service. This is not an offline model. Houdini and Windows still load their own runtime files. The checked tools are an application boundary, **not an OS sandbox for a malicious `.hip`, third-party plugin or another process running as you**. Long Houdini cooks can still block its UI; Stop cannot roll back completed edits.

## Updating from 0.5.x

Close the old assistant and install 0.6.0 into a fresh package folder. Disable the old package so only one version loads. Sign in through the new setup UI. Old global chats, downloaded textures and caches are not imported or deleted. Keep the old installation if existing scenes reference its assets. The old global chat catalogue is intentionally not offered in the scene-specific chat list.

## Development

See [Development](docs/DEVELOPMENT.md), [Architecture](docs/ARCHITECTURE.md), [agent guidance](AGENTS.md) and [release checklist](docs/RELEASE_CHECKLIST.md), and [0.6.0 handover](docs/HANDOVER.md). Original project code is MIT; bundled software keeps its own licenses, described in [THIRD_PARTY.md](THIRD_PARTY.md).
