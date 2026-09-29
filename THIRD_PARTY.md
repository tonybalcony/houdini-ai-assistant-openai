# Third-party software

The MIT license applies to original project code only. It does not relicense Houdini, Codex, model services, assets or dependencies.

The 0.6 artist ZIP includes portable Python 3.13.15, the official OpenAI Codex Windows x64 runtime 0.157.1 and 40 exact-version Python distributions from `requirements-lock.txt`. Binaries remain excluded from Git. Original Python license text, Codex LICENSE/NOTICE and Python distribution license metadata are retained in `.runtime`. `manifest.json` records original download URLs, archive/wheel hashes and shipped-file hashes. Unused pip CLI launchers and local download-origin metadata are omitted.

[Codex source and release](https://github.com/openai/codex/releases/tag/rust-v0.157.1) and [Python](https://www.python.org/) have their own licenses. The upstream Houdini MCP package is no longer downloaded, executed or redistributed. The Python MCP libraries that remain are transitive Agents SDK dependencies; they do not start a Houdini MCP server.

Houdini/Karma require a SideFX license. Each user supplies their own subscription/API access, with separate billing. Uthana is optional and separately licensed/billed; no generated assets are shipped. Dependencies retain their own terms. Pinning and artifact hashes are not a completed license or vulnerability audit.
