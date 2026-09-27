# Houdini AI Assistant (OpenAI)

A conversational assistant inside Houdini that can inspect, build and edit your current scene. Chat in a Python Panel, keep conversations between sessions, animate APEX characters, and iterate on Solaris lookdev with render previews.

**Version 0.5.0 - first public preview - Windows / Houdini 22**

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
| **API / billed by tokens** | Your API key, entered in setup | Separate API billing; Agents SDK and dedicated scene/APEX/lookdev tools. |

There is **no automatic switch** to API billing or another model. The selector offers GPT-6 Astra, GPT-5.6 Sol and GPT-5.6 Terra. Missing account access produces an error, not substitution.

## Requirements

- Windows 10/11, 64-bit; tested with **Houdini 22.0.368** and PySide6.
- A licensed Houdini installation. Karma XPU needs compatible hardware/drivers.
- Internet access for installation and model use.
- A writable installation folder with space for Python environments and Codex.
- Subscription: a ChatGPT account with access to Codex/the selected model.
- API: an OpenAI API key, model access and API billing.
- Optional: your own Uthana account/credits and local texture library.

Python, dependencies and Codex are prepared by the setup window. Existing supported installations can be reused; no terminal is needed for normal installation. This release supports Windows x64 only.

## Install the plugin

1. Download the **plugin archive** `houdini-ai-assistant-0.5.0.zip` supplied with the release. This is different from GitHub's automatic **Source code (zip)** download.
2. In Houdini, choose **File > Install Package Archive...**, select the ZIP and choose your Houdini user **packages** folder as the installation location. Restart Houdini after installation.
3. Enable the shelf through **shelf [+] > Shelves > AI Assistant**, then click **Open Assistant**.
4. In the setup window, choose **ChatGPT subscription** or **OpenAI API key**, then click **Continue**. Setup downloads and verifies the required software in the background.
5. Complete browser sign-in, or paste your own API key into the masked field. Click **Open assistant** when connected.

The next time you launch from the shelf, the assistant opens and connects using the remembered setup. You do not need to sign in each time. Revoked/expired credentials can require signing in again; use **Account** in the panel to repeat setup or change the connection method.

Houdini also supports dragging a package ZIP into its window. See [SideFX's package installation guide](https://www.sidefx.com/docs/houdini/ref/windows/package_browser.html). This repository is currently prepared locally; the downloadable release will be available after publication.

### Install by copying files

Extract the plugin ZIP into your Houdini user packages folder. Keep **both** items alongside one another:

```text
<Houdini user preferences>/packages/
  houdini-ai-assistant.json
  houdini-ai-assistant-openai/
    open_panel.py
    toolbar/astra.shelf
    ...assistant source...
```

Use Houdini's Package Browser to locate the user package directory. On many Windows installations it is under `Documents/houdini22.0/packages`; OneDrive or custom preferences can change this location. [Houdini scans package JSON files directly inside that folder, not arbitrary nested repositories.](https://www.sidefx.com/docs/houdini/ref/plugins.html)

If using a Git clone or GitHub's source ZIP, name its folder **houdini-ai-assistant-openai**, place it inside packages, and copy its `houdini-ai-assistant.json` **one level up** into packages. Restart Houdini and use the same shelf/setup steps. Do not copy another person's prepared runtimes, credentials or chat history.

### How sign-in and setup work

- **Subscription:** Codex's native [App Server login](https://learn.chatgpt.com/docs/app-server) opens the browser. The assistant reuses an existing ChatGPT sign-in when available. Codex manages its own credentials; the assistant never stores your ChatGPT password. Subscription mode rejects API-key logins.
- **API:** create your own key on the [OpenAI platform](https://platform.openai.com/api-keys), then paste it into setup. The key is checked without generating a response and encrypted using Windows DPAPI for the current Windows user. API usage has separate billing; ChatGPT subscriptions do not supply API credits.
- Account preferences and the encrypted API key live in `%LOCALAPPDATA%/HoudiniAstra`. They stay outside the plugin/source folder. Existing `OPENAI_API_KEY` environment configuration still works; a key saved in setup takes precedence.
- Setup uses signed official Python and Codex runtimes, pinned dependency versions and a checksum-verified [Houdini MCP download](THIRD_PARTY.md). It creates private environments inside the plugin folder. Nothing is installed into Houdini's embedded Python, and global Codex configuration is not rewritten.
- First setup can take several minutes. **Open setup log** helps diagnose installation errors; **Retry** continues setup. Cancellation waits for the current installer step to finish. No model request is sent during setup.

Never paste keys into chat prompts, shelf scripts, screenshots or Git commits. A `.env` file is not automatically loaded. Do not disable Windows security if a runtime is blocked; see [troubleshooting](DEVELOPMENT.md#troubleshooting).

## Use the assistant

Open **AI Assistant > Open Assistant**, wait for Ready, then **Send** or **Ctrl+Enter**. You can select a model in the panel; switching backend/model starts a separate conversation. Use **Connect** to retry a disconnected session.

For developers using a source folder outside packages, the existing Python Source Editor entry still works and now opens the same setup UI:

In **Windows > Python Source Editor**, run this with the actual source folder:

```python
import runpy
runpy.run_path(r"C:/path/to/houdini-ai-assistant-openai/open_panel.py")
```

The launcher generates an ignored, machine-local panel file automatically; no source path edits are needed.

Example prompts:
- Explain this network, then add a mountain deformation to the selected sphere.
- Inspect this Scene Animate character and put a gentle head turn on a new override layer.
- Bring this SOP into Solaris, build a MaterialX material, make a working XPU render and inspect its preview.

**Stop** rejects queued dedicated actions; completed edits remain. It cannot interrupt every running cook or cancel an accepted Uthana job. Background renders have their own cancel tool. **Undo last edit** handles the latest dedicated Astra batch; MCP edits may need Houdini Undo.

**Saved chats** restores history and drafts; click Connect to continue. **New chat** preserves earlier conversations. Changing backend/model creates a separate conversation. Save your `.hip` normally: chat persistence does not save your scene.

Restart Houdini after updating the plugin. Reconnecting an existing widget does not reload its code. Keep the installation in a stable, writable location; moving it requires recreating its Python environments. There is no automatic update service.

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
- Setup has been checked in an isolated installation folder on an existing Windows workstation. A fresh Windows OS and another person's interactive browser sign-in have not been tested.

## Development and license

Houdini loads Python source. Developers can use `setup.ps1` with signed Python 3.13 and build a source-only package ZIP from the audited Git index:

```powershell
./setup.ps1 -PythonExe 'C:/path/to/signed/Python313/python.exe'
& ./.venv/Scripts/python.exe -m unittest test_worker test_codex_worker test_uthana test_mcp test_models test_chat_history test_diagnostics test_packaging test_onboarding
& ./.mcp-venv/Scripts/python.exe -m unittest test_texture_tools
& ./.venv/Scripts/python.exe scripts/build_plugin.py
```

These tests make no model calls. See [DEVELOPMENT.md](DEVELOPMENT.md) for native checks, live-test costs and diagnostics; [AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md) for implementation guidance.

See [CHANGELOG.md](CHANGELOG.md), [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [THIRD_PARTY.md](THIRD_PARTY.md). Original code is licensed under [MIT](LICENSE).
