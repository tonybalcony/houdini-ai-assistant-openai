# Solaris lookdev, textures and connection recovery

Updated 13 September 2026 for Houdini 22.0.368.

## Start using it

Close the Astra panel and reopen it from your existing shelf button. Choose a saved chat or start a new one, then click **Connect**. The rules apply to Astra, Sol and Terra, and to both Subscription and API modes. Resuming a subscription chat updates the instructions and loads the new MCP tools without losing the conversation.

Try: “Bring the selected SOP into Solaris, give it a MaterialX material and a simple lighting setup. Make a working Karma XPU render, inspect its WIP image, and stop early if the framing needs changing.”

## The rendering and material rules

- Render scenes using Karma XPU in Solaris. Do not use Mantra, Karma CPU, OpenGL scene renders or an `/out` render setup.
- Create lighting with Solaris USD light nodes.
- Create materials with MaterialX networks inside Solaris Material Libraries and bind them to USD primitives.
- Preserve existing scene work. Build a new branch when converting a legacy setup.

The upstream MCP has generic node tools and Karma options, but its render helpers create ROPs in `/out`, and its material helper defaults to a Principled Shader. The assistant now disables those legacy render/material helpers and adds dedicated tools. Generic node creation rejects Mantra/Principled/Classic shaders, object lights, and `/out` Karma ROPs. General Houdini Python remains available under the upstream normal policy and the standing instructions; these workflow rules are not an operating-system security sandbox.

The custom tools create SOP Imports, Material Libraries with real MaterialX Builders, USD lights and cameras, and Karma Render Settings. Inspection reads the composed USD stage and its actual prims and bindings. A render can only start from an inspected Solaris Karma settings node with `engine=xpu`. No other render engine is selected on failure. This follows SideFX's [Material Library](https://www.sidefx.com/docs/houdini/nodes/lop/materiallibrary.html) and [Karma XPU](https://www.sidefx.com/docs/houdini/solaris/karma_xpu.html) workflows.

## Working renders and seeing a WIP

Render tools launch Houdini's `husk` renderer in a separate local process. First, the current frame of the Solaris stage is exported to a private USD snapshot. A render job then continues independently of the chat process, with an ID that can be used after reconnecting.

Use `quality=working` for lookdev. The exported snapshot uses at most a 960-pixel longest edge and 32 path-traced samples. Diffuse bounces are capped at 1, reflection/refraction at 2, and secondary volume/SSS bounces at 0. Material displacement connections are disabled, along with depth of field and motion blur. These changes apply to the snapshot; the artist's original nodes, displacement wiring and final settings remain intact. Use `quality=final` only when the user requests a final image.

Karma saves intermediate snapshots periodically. The render helper converts readable snapshots into small JPEG previews. `houdini_solaris_render_preview` returns an actual image to the model, not a base64 string presented as text. Astra is instructed to inspect that image while rendering is still running, judge composition and broad lighting/material appearance, and cancel before revising a bad setup. Quick renders may finish before an intermediate image is written. Noisy previews cannot establish final image quality or judge disabled displacement, depth of field and motion blur. Reduced refraction can also misrepresent deep glass.

`houdini_solaris_render_status` can wait up to ten seconds, returning early when a new preview appears or the render ends. This avoids rapid polling and runs outside Houdini's UI thread in the assistant. `houdini_solaris_render_cancel` cancels an identified render. The panel's **Stop** stops the assistant turn; an already-started background render is a separate job. Reconnect and say “List my render jobs and cancel the latest running job” if necessary. It never automatically restarts an interrupted render.

The jobs and USD snapshots live in `.render_jobs/`. A working render defaults to a unique PNG; a final render defaults to a unique EXR. An explicitly requested output path must be an absolute PNG/EXR path that does not already exist. External assets referenced by the USD must remain accessible. The snapshot export can still take time on a heavy scene, even though image rendering happens in the background. SideFX documents the underlying [husk snapshot options](https://www.sidefx.com/docs/houdini/ref/utils/husk.html).

**Machine-specific finding:** the test renderer reported `Failed to initialize Optix 90000` and an unsupported ABI, with a message that a 570+ driver is required. A small Karma XPU image still completed using available devices. This proves XPU engine execution, but does not verify GPU acceleration. Jobs surface the warning so Astra can report it. This update does not change GPU drivers or select Karma CPU.

## Textures and Megascans

Configure your library using `HOUDINI_ASTRA_TEXTURE_LIBRARY` or the ignored `local_settings.json`; without one, only the assistant texture cache is searched. `texture_library_search` searches folders and filenames and reports likely map roles. It sees new files on the next search. The library is read without modifying originals.

`texture_download` accepts an authorized HTTPS file link and writes an image or bounded image-only ZIP extraction to `texture_cache/`. It verifies image content, rejects private-network URLs, records a source reference with signed query parameters removed, and preserves existing filenames. It does not upload scene data or submit Epic passwords. `texture_write` writes solid, checker, gradient and seeded-noise PNGs. Use modest resolutions for working lookdev.

`houdini_materialx_textures` connects base color, roughness, metalness, normal and displacement maps to a Solaris MaterialX Standard Surface. It uses sRGB texture color for base color and Raw for data maps. Supply OpenGL +Y normal maps and inspect the geometry's UVs; the tool does not create UVs. For a material built with these tools, displacement remains connected for final rendering and is disabled only in a working snapshot.

**Automatic authenticated Fab acquisition is not implemented.** Do not provide Epic passwords to the assistant. For protected assets, use the signed-in Fab/Epic Games Launcher to download them into your library, or supply an authorized direct file link. Astra can then find/connect them. Product pages are not download links and the assistant does not make purchases. See the [Fab download workflow](https://dev.epicgames.com/documentation/fab/exporting-assets-from-fab-in-launcher).

## What caused yesterday's interruptions

The saved conversation contained two “Codex or Houdini timed out” messages. The corresponding Codex session showed:

| Request started (UTC) | Aborted (UTC) | Duration |
|---|---|---|
| 12 September, 11:52:21.631 | 12:02:21.181 | About ten minutes |
| 12 September, 12:03:12.008 | 12:13:11.485 | About ten minutes |

The adapter imposed a fixed ten-minute limit on the entire turn. That limit expired even when MCP calls continued completing. This is strong evidence that our adapter cutoff caused those two interruptions; the previous code discarded low-level errors, so other past failures cannot be reconstructed completely.

The turn watchdog now measures ten minutes **without model/turn activity**, rather than total elapsed work. Stale events and account heartbeats do not extend it. Individual RPC and scene-tool deadlines remain, with distinct error messages, so a stuck tool is still detected. The API worker also uses inactivity detection for its response stream.

## Logs for the next incident

Click **Logs** in the panel to open `.logs/`. Panel, Codex/API worker, MCP and render processes write timestamped JSON-lines diagnostics. The logs record process exits, protocol errors, connection ports, conversation/run/call identifiers, tool names, durations and distinct timeout causes. MCP render-job IDs can be matched to renderer logs and `.render_jobs/<job_id>/state.json`.

Each process log rotates at 2 MB with two backups. Older diagnostic files are pruned after the retained-file threshold and age limit. Prompt, code, environment and tool-result payload fields are excluded. Credential-like strings are redacted from error messages. Raw SDK stderr is reduced to error categories and byte counts. Chat transcripts still have their separate existing local storage; logs do not replace it. Render manifests retain a short renderer error tail for practical troubleshooting.

If it happens again, note the time and leave the logs in place. Reconnect the saved chat and ask Astra to inspect the current scene before continuing. Unknown-result mutations and paid motion generation should not be repeated blindly.

## Verification

The checks cover exact model/tool schemas, timeout behavior, stale events, log redaction/rotation, texture file validation and no-overwrite behavior, real Houdini Qt/saved-chat behavior, native USD material binding and texture connections, and the real Codex-to-MCP connection. A small Karma XPU image was produced, and the native MCP preview returned image content. The separate WIP check exercises intermediate-image availability and early cancellation. Tests use disposable scenes; your open scene is not changed.

Relevant checks: `test_diagnostics.py`, `test_texture_tools.py`, `check_solaris.py --render --wip`, and `check_mcp.py --solaris`. No model turns are needed. Texture fixtures are synthetic. The MCP preview assertion needs the report from a preceding render check and explicitly reports a skip otherwise. See [DEVELOPMENT.md](DEVELOPMENT.md).
