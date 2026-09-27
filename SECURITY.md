# Security and privacy

Tools can edit the live Houdini scene. Use a trusted local workstation, keep scene backups and review results. Loopback-only MCP is not a security boundary against malicious local users or hostile code.

Each user supplies their own credentials. API keys entered through setup are encrypted with Windows DPAPI and saved outside the source folder in `%LOCALAPPDATA%/HoudiniAstra/api-key.dpapi`. This protects the file at rest for the Windows account; it is not protection against code running as that user. The API worker decrypts it locally and sends it only to OpenAI for authentication. A saved key takes precedence over the legacy `OPENAI_API_KEY` environment variable.

Codex handles browser sign-in and persists its own account state. The setup helper communicates through private process pipes, never command-line credential arguments. It checks the API models endpoint without sending a model request, refuses redirects on that credential-bearing request, and uses an HTTPS allowlist for opening Codex login URLs. The assistant does not collect a ChatGPT password.

Uthana credentials remain in each user's environment or the documented ignored key file. Never attach keys, Codex auth files, chat databases, assets or raw logs to public issues. Source releases contain no maintainer login state. To remove an API key saved by setup, close the assistant and delete `api-key.dpapi` from the user data folder; deleting `preferences.json` also resets the first-run choice. Codex sign-out is managed by Codex.

Prompts, scene context and tool results go to the selected model service. Uthana gets motion descriptions/settings only. Local chat history and optional Uthana secret files are not encrypted.

Bootstrap downloads pinned Python and Codex artifacts over HTTPS, verifies SHA-256 and Windows publisher signatures before execution, and leaves Windows security policy intact. The source-only plugin archive contains no executable runtimes. Python packages are version-pinned but do not yet have complete artifact hash locks. The installation folder must be writable; this preview is intended for a per-user installation rather than shared untrusted writable storage.

Logs redact credential-like errors and exclude payload fields, but filenames, screenshots and reports may remain private. Review before sharing.

For vulnerabilities, use GitHub private vulnerability reporting if enabled. If unavailable, first request a private contact channel without posting sensitive details. Never disclose credentials in a public issue. This community preview has no guaranteed response time.

Only the current preview is maintained. Third-party dependencies have their own policies; version pinning is not a completed vulnerability audit.
