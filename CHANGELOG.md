# Changelog

## 2026-06-09 — reliability hardening + notifications

### Fixed
- **Daily crash**: `IPHONE_IMAGE_DIR` left as the `.env.example` placeholder
  (`/Users/YOUR_USERNAME/...`) made `ensure_dirs` fail before the wallpaper was set.
  The iPhone feature is now isolated — a bad or placeholder iCloud path is reported and
  skipped, and the **Mac wallpaper always updates** regardless.
- Config now expands `~` and `$VARS` in `IMAGE_DIR` and `IPHONE_IMAGE_DIR` (the
  placeholder trap came from paths not expanding).
- Placeholder Are.na token/slug are now rejected with a clear message instead of the
  script running with fake credentials.
- Network failure at boot no longer crashes the run — the Are.na sync is skipped and the
  wallpaper rotates off existing local images.

### Added
- curl timeouts (`--connect-timeout`/`--max-time`) on all requests, so a stalled host
  can't hang the unattended agent.
- Atomic `.state.json` writes; pruning of local files for blocks removed from the
  channel; `arena_wallpaper.log` rotation at ~1 MB (one `.1` backup).
- Optional **ntfy notifications** (off unless `NTFY_URL` is set in `.env`): a
  high-priority alert on hard failures and one quiet summary per day. No emojis.
  `NTFY_URL`/`NTFY_TOKEN` live only in the gitignored `.env`, so other users of the repo
  are unaffected.
- `CLAUDE.md` (agent/debugging guide).

### Changed
- iCloud iPhone-wallpaper folder moved to
  `~/Library/Mobile Documents/com~apple~CloudDocs/sandbox/arena-wallpaper/images-iphone`.
- `TARGET_WIDTH` default corrected to 720 (to match the docs); `requirements.txt` pinned;
  curl download uses `-fsSL`; `load_dotenv(override=True)`.
- The Are.na request retry keeps the token in the `Authorization` header (never the URL).

## 2026-06-01 — first public release

- Replaced the Homebrew `wallpaper` CLI with `pyobjc` (NSWorkspace) — no external CLI.
- Dynamic project root via `Path(__file__).parent.resolve()`.
- Published to GitHub: https://github.com/sjoerd-mol/arena-wallpaper
