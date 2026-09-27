# Contributing

Read [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md) and [DEVELOPMENT.md](DEVELOPMENT.md). Keep changes focused and describe resulting behavior, test evidence and compatibility impact.

- Keep HOM work on Houdini's main thread, networking outside it.
- Preserve separate billing, exact model selection, history recovery and cancellation guards.
- Extend shared contracts and both relevant backend routes when adding tools.
- Keep MCP loopback-only with upstream normal policy.
- Use Solaris/Karma XPU/MaterialX and local Uthana retargeting.
- Use synthetic fixtures and temporary chat stores; do not share private scenes/assets/logs.
- Run relevant offline tests first; document skipped native/live checks.
- Bug reports should include OS, Houdini version, backend and a minimal synthetic reproduction. Never include keys.
- The flat module layout is intentional for Houdini loading in this preview. Broad module moves or formatting are unnecessary.
- Do not silently update upstream revision, dependencies, model IDs or billing behavior.
