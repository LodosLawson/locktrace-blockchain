# LockTrace Blockchain Agent Guidelines & Synchronization Rules

## Repository Information
- **Repository**: `LodosLawson/locktrace-blockchain`
- **Default Branch**: `master`
- **MCP Server**: `github` (Model Context Protocol)
- **Live Mainnet**: `https://locktrace.space`
- **Stitch MCP Design Project**: `Modern Crypto Wallet App` (`projects/3922358138058284555`)
  - Space - Takipçiler (Followers): `projects/3922358138058284555/screens/8eaf844dee6a4e35af88efa9367b5f7a`
  - Space - Takip Edilenler (Following): `projects/3922358138058284555/screens/ddf7194e85b64ccaab2e59cf3d82aba4`

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

4. **No Stitch Sample/Mock Data Policy:**
   - Stitch templates default to sample/mock data (e.g. `Kullanıcı 1`, `vitalik_eth`, fake followers, fake counts).
   - NEVER include hardcoded sample/mock data from Stitch in production code.
   - Always connect real on-chain ledger/API data (`currentProfileData.followers`, `currentProfileData.following`, real balances and counts).
   - If no on-chain data exists yet, always display a clean, contextual empty state.
