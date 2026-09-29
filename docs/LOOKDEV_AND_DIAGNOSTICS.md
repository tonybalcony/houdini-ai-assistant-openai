# Look development and diagnostics — 0.6.0

Lighting is authored in Solaris, materials in MaterialX and rendering in Karma XPU. The checked Solaris tool creates SOP imports, lights, cameras, materials and render settings. Unsupported nodes or outside dependencies return Access denied; do not bypass that error with code or another render engine.

Texture search, generation, download and the texture-binding helper are removed. Existing user caches remain untouched. Material color/roughness/metalness can still be authored with checked tools.

Save the scene before rendering. Default outputs, USD snapshots, manifests and previews live under `$HIP/.astra/<scene-id>/renders/<job-id>/`. An explicit output must remain in the current saved `$HIP`, use PNG/EXR and not already exist. External asset dependencies are checked before launching husk.

Working snapshots cap resolution at 960 pixels on the longest edge and samples at 32, reduce secondary rays and disable displacement, depth of field and motion blur. Original scene settings remain intact. Inspect an actual WIP preview, cancel an unhelpful job and improve the scene; status text alone is not visual evidence. Final quality is explicit.

Logs live in the plugin's `.state/logs`; setup diagnostics in `.state/setup.log`. The Logs button opens the current folder. Payloads and prompts are excluded, but paths may be private. Correlate session/run/call identifiers before sharing a redacted excerpt. A stale job is unknown, not automatically failed or safe to rerun. Stop cannot forcibly interrupt a live HOM cook.
