# Houdini AI Assistant (OpenAI)

A conversational assistant inside Houdini that can inspect, build and edit your current scene. Chat in a Python Panel, keep conversations between sessions, animate APEX characters, and iterate on Solaris lookdev with render previews.

**Version 0.4.0 - first public preview - Windows / Houdini 22**

An independent community project, not an official OpenAI, SideFX or Uthana product. It uses your own accounts; model availability depends on your account.

## Features

- Explain, create, connect and edit Houdini node networks.
- Animate exposed APEX Scene Animate controls and layers.
- Optionally generate Uthana motion and retarget it locally onto an existing humanoid rig.
- Create Solaris lighting and MaterialX materials, and render with Karma XPU.
- Inspect intermediate render images with reduced-cost working settings.
- Search local textures, download authorized files and write procedural textures.
- Save conversations and drafts, with fresh scene inspection on reconnect.

| Backend | Your authentication | Billing and tools |
|---|---|---|
| **Subscription / Codex** (default) | ChatGPT sign-in in Codex | Shared Codex allowance; dedicated tools plus local Houdini MCP. |
| **API / billed by tokens** | `OPENAI_API_KEY` | Separate API billing; Agents SDK and dedicated scene/APEX/lookdev tools. |

There is **no automatic switch** to API billing or another model. The selector offers GPT-6 Astra, GPT-5.6 Sol and GPT-5.6 Terra. Missing account access produces an error, not substitution.

## Requirements

- Windows 10/11, 64-bit; tested with **Houdini 22.0.368** and PySide6.
- A licensed Houdini installation. Karma XPU needs compatible hardware/drivers.
- Official **64-bit Python 3.13** from [python.org](https://www.python.org/downloads/windows/) with a valid publisher signature. Do not install dependencies into Houdini's embedded Python.
- Internet access for installation and model use.
- Subscription: installed [Codex CLI or desktop](https://learn.chatgpt.com/docs/codex/cli), ChatGPT sign-in and access to Codex/the selected model.
- API: an OpenAI API key, model access and API billing.
- Optional: your own Uthana account/credits and local texture library.

## Install

Download/extract this repository's source ZIP or clone it into a writable folder. Open PowerShell **inside that folder** and run:

```powershell
./setup.ps1
```

Setup discovers `py -3.13` or an existing local `.python313` installation. To supply Python explicitly:

```powershell
./setup.ps1 -PythonExe 'C:/path/to/Python313/python.exe'
```

Setup creates two private environments, installs pinned dependencies, fetches a checksum-verified [Houdini MCP revision](THIRD_PARTY.md), and checks package compatibility. Both environments are needed for the complete tool set, including API-mode texture/render helpers. Nothing is installed into Houdini's embedded Python, and global Codex settings are not changed.

Follow your organization's PowerShell policy if scripts are blocked. Do not disable Smart App Control. Use a trusted signed Python installation; see [troubleshooting](DEVELOPMENT.md#troubleshooting).

### Use your own subscription

Install Codex using the [official instructions](https://learn.chatgpt.com/docs/codex/cli), then sign in through Codex desktop or run:

```powershell
codex login
codex login status
```

[Codex login](https://learn.chatgpt.com/docs/developer-commands#codex-login) opens a browser for ChatGPT authentication. Complete it with **your own account**. The assistant reuses that local sign-in; it does not ship the author's session or provide a separate login form. Select **Subscription / Codex** in the panel. API-key Codex logins are rejected in this mode.

If discovery fails, set the user environment variable `HOUDINI_ASTRA_CODEX` to your actual `codex.exe` path, then restart Houdini.

### Use your own API key

Create a key in the [OpenAI API platform](https://platform.openai.com/api-keys). In Windows **Environment Variables > User variables**, add `OPENAI_API_KEY` with your key and restart Houdini. Choose **API / billed by tokens** in the panel. This backend does not require Codex sign-in. ChatGPT subscriptions do not supply API credits.

Never paste keys into prompts, shelf scripts, screenshots or Git commits. A `.env` file is not automatically loaded by this assistant.

## Open in Houdini

In **Windows > Python Source Editor**, run this with the actual source folder:

```python
import runpy
runpy.run_path(r"C:/path/to/houdini-ai-assistant-openai/open_panel.py")
```

The launcher generates an ignored, machine-local panel file automatically; no source path edits are needed. Use the same two lines in a Python shelf tool for convenience.

Select backend/model, click **Connect**, wait for Ready, then **Send** or **Ctrl+Enter**.

Example prompts:
- Explain this network, then add a mountain deformation to the selected sphere.
- Inspect this Scene Animate character and put a gentle head turn on a new override layer.
- Bring this SOP into Solaris, build a MaterialX material, make a working XPU render and inspect its preview.

**Stop** rejects queued dedicated actions; completed edits remain. It cannot interrupt every running cook or cancel an accepted Uthana job. Background renders have their own cancel tool. **Undo last edit** handles the latest dedicated Astra batch; MCP edits may need Houdini Undo.

**Saved chats** restores history and drafts; click Connect to continue. **New chat** preserves earlier conversations. Changing backend/model creates a separate conversation. Save your `.hip` normally: chat persistence does not save your scene.

Close and reopen the panel after updating source. Reconnecting an existing widget does not reload its code.

## Optional integrations

**Uthana:** configure your own `UTHANA_API_KEY` environment variable or put only the key in ignored `.secrets/uthana_api_key`. Generation has separate Uthana costs. Only motion text/settings go to Uthana; your rig stays local. Retargeting needs a suitable biped and can require manual mapping. Clips span 4-10 seconds. Check cached jobs after interruptions before starting another paid generation.

**Textures:** copy `local_settings.example.json` to ignored `local_settings.json` and set `texture_library` to your folder, or set `HOUDINI_ASTRA_TEXTURE_LIBRARY`. With neither configured, search uses the assistant's own cache. Library files are preserved. Automatic Fab/Epic sign-in/acquisition is not implemented; download licensed assets yourself or supply an authorized direct file URL.

**Lookdev:** rendering uses Solaris/Karma XPU, lighting uses Solaris, materials use MaterialX. Working snapshots reduce resolution/samples and disable displacement/DOF/motion blur while preserving final scene settings. See [the lookdev guide](LOOKDEV_AND_DIAGNOSTICS.md).

## Privacy and limitations

- Prompts, scene context and tool results go to the chosen model service; this is not an offline model.
- Local chat history is unencrypted. Subscription history also needs Codex's own session storage.
- MCP is loopback-only for a trusted local workstation, not a public server or hostile-code sandbox.
- Tools edit live scenes. Failed batches can partially apply; save scene versions and inspect before retries.
- Long cooks can block the UI. No general auto-rigger or world-space IK solver is supplied.
- XPU engine execution does not itself prove GPU acceleration; drivers and devices matter.
- macOS/Linux and other Houdini versions are not validated. Docking/focus and artistic motion quality need manual review.
- Keep source in a stable writable location. Moving it requires recreating virtual environments and updating the shelf path.

## Development and license

There is no compiled application build. Setup prepares Python environments and Houdini loads the source.

```powershell
& ./.venv/Scripts/python.exe -m unittest test_worker test_codex_worker test_uthana test_mcp test_models test_chat_history test_diagnostics test_packaging
& ./.mcp-venv/Scripts/python.exe -m unittest test_texture_tools
```

These tests make no model calls. See [DEVELOPMENT.md](DEVELOPMENT.md) for native checks, live-test costs and diagnostics; [AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md) for implementation guidance.

See [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [THIRD_PARTY.md](THIRD_PARTY.md). Original code is licensed under [MIT](LICENSE).
