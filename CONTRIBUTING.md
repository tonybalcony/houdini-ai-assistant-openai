# Contributing

Read [AGENTS.md](AGENTS.md), [Architecture](docs/ARCHITECTURE.md), [Development](docs/DEVELOPMENT.md) and [Security](SECURITY.md). Describe behavior, tests and limitations in each change.

- Preserve the plugin/current-saved-HIP boundary, checked tools and disabled unrestricted execution.
- Keep network work outside Houdini and scene operations on its main thread.
- Preserve separate billing, exact models, cancellation/idempotency and scene-specific history.
- Use Solaris, Karma XPU and MaterialX. Uthana retargeting stays local.
- Use synthetic fixtures and dummy credentials. Never share private scenes, account files or raw logs.
- Run relevant offline tests; report skipped native/license/live checks honestly.
- Keep generated runtimes and all user state out of Git. Release binaries are assembled only through the manifest-based builder.
