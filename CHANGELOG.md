# Changelog

## 2026-09-26 — fill color, silent API errors, safer pruning

### Fixed
- **Fill color reset to blue.** macOS keeps the wallpaper fill color per Space and per
  display, and does not always report it: for about 2 seconds after a change it reports
  none, and it seems to do the same for a Space/display pair it has not stored yet.
  The script then passed no color, and macOS used its default blue (65, 105, 170).
  After that, the preserve step kept the blue. Now:
  - `WALLPAPER_FILL_COLOR=#RRGGBB` in `.env` pins the color on every screen;
  - without it, the last color seen per display (by name) is kept in `.state.json` and
    reused when macOS reports none.
- **Wrong token or channel slug was silent.** Are.na answers a 401/404 with a JSON error
  body, which looked like an empty channel ("Sync complete. New images: 0"). This is now
  a hard failure: logged, and a high-priority ntfy alert. The wallpaper still rotates
  from local images. 401/403/404 are not retried.
- **Pruning** only runs when the number of blocks received matches the API's
  `total_count`, and refuses to delete more than 25% of local images at once (floor
  of 5). A short or broken page can no longer delete the library.
- `RECENT_DAYS` now also applies when `PER_SCREEN_RANDOM=false`.
- A download whose Are.na filename has no image extension gets one from its
  `content_type`; before, it was marked as downloaded but never shown.
- An invalid number in `.env` (e.g. `TARGET_WIDTH=720px`) logs a warning and uses the
  default instead of crashing. A blank `TARGET_WIDTH=` / `RECENT_DAYS=` still means 0.

### Changed
- `requirements.txt`: `Pillow>=10,<13` (12.x is what runs in practice).
- `--dry-run` prints a readable error for a bad token/slug, shows block `type` for
  non-image blocks, and reports whether the listing was complete.

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
