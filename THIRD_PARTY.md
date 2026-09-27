# Third-party dependencies

The project MIT license applies to this repository's original source. It does not
relicense Houdini, Codex, model services, downloaded assets or external dependencies.
No credentials, binary runtimes, third-party assets or upstream source archives are
included in this repository.

## Houdini MCP

Setup downloads [oculairmedia/houdini-mcp](https://github.com/oculairmedia/houdini-mcp)
at revision `7e5cd7a2484b899a6e9251c6f7b90228c2ec7990` into the ignored `vendor/`
directory. The archive's SHA-256 is pinned in `install_mcp_source.py`. The upstream
Python sources are unmodified; project extensions live in `mcp_extensions.py`.

The pinned upstream `pyproject.toml` declares MIT. That revision does not contain a
standalone license/copyright notice. We link to and fetch the original upstream
project rather than redistributing a reconstructed license or vendor copy.
Consult upstream before separately redistributing its source. Its own metadata and
attribution remain in the downloaded source tree.

## Python dependencies and services

`requirements-lock.txt` and `requirements-mcp-lock.txt` record tested dependency
versions, including OpenAI/Agents SDK, FastMCP, RPyC, HTTPX and Pillow. Packages are
installed from the package index and retain their respective licenses; consult their
installed distribution metadata. Version locks do not constitute a license or
vulnerability audit and do not pin artifact hashes.

Houdini and Karma require a SideFX installation/license. Codex subscription access,
OpenAI API access and Uthana access are supplied by each user and have separate
terms and billing. Megascans/Fab assets must be obtained and used under the user's
applicable license; none are shipped as examples or fixtures.
