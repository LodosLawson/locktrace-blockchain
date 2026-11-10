# LockTrace Blockchain Agent Guidelines & Synchronization Rules

## Repository Information
- **Repository**: `LodosLawson/locktrace-blockchain`
- **Default Branch**: `master`
- **MCP Server**: `github` (Model Context Protocol)
- **Live Mainnet**: `https://locktrace.space`

## Mandatory Synchronization Policy

Whenever significant updates, security fixes, whitepaper revisions, or version bumps are made:

1. **Full Parity Check:**
   - Synchronize `README.md`, `docs/WHITEPAPER.md`, `frontend/docs/WHITEPAPER.md`, and `docs/LOCKTRACE_NOTION_WORKSPACE.md`.
   - Update `PROTOCOL_VERSION` in `config.py`, `node_runner.py`, `package.json`, and frontend files.

2. **GitHub Synchronization:**
   - Always commit staged changes with semantic commit messages (e.g. `feat:`, `fix:`, `docs:`, `security:`).
   - Push to GitHub remote (`origin master`).
   - Use the **GitHub MCP Server** (`github` tools: `list_commits`, `get_file_contents`, `create_or_update_file`, `push_files`) to verify that the remote repository is in sync and accurately reflects the local state.

3. **Production Deployment:**
   - Run `python scripts/fast_deploy.py` to deploy hardened code to the VPS host (`https://locktrace.space`).
