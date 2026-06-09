# arena-wallpaper

A Python tool that pulls images from an [Are.na](https://www.are.na) channel and uses them as rotating wallpapers on your Mac and iPhone. Images are synced daily, with a different image set on each connected screen. On iPhone, pre-composed wallpapers are delivered silently via iCloud and set automatically through a Shortcuts automation.

> **Apple ecosystem only.** This tool is built around macOS, iCloud Drive, and iOS Shortcuts. It does not run on Windows or Linux.

---

## How it works

The script runs once a day via a background task (LaunchAgent). It does two things:

1. **Syncs new images** from your Are.na channel to a local folder on your Mac.
2. **Sets a random wallpaper** on each connected screen, picking a different image per screen and avoiding recent repeats.

At the same time, it generates iPhone-sized versions of every image and writes them to an iCloud Drive folder. An iOS Shortcut reads from that folder on a schedule and silently sets your iPhone wallpaper.

---

## Requirements

- macOS 13 or later
- Python 3.12 or later — install via Homebrew: `brew install python`
- An [Are.na](https://www.are.na) account with at least one channel containing image blocks
- iCloud Drive enabled on your Mac (for iPhone wallpapers)
- iPhone with Shortcuts (for iPhone wallpapers)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/sjoerd-mol/arena-wallpaper.git
cd arena-wallpaper
```

### 2. Create a Python environment and install dependencies

```bash
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> If `brew install python` installed a different version, check what's available: `ls /opt/homebrew/bin/python*`

### 3. Configure

Copy the example config file and open it in a text editor:

```bash
cp .env.example .env
open -e .env
```

The two required values are:

- **`ARENA_ACCESS_TOKEN`** — your Are.na personal access token. Generate one at [are.na/settings/personal-access-tokens](https://www.are.na/settings/personal-access-tokens).
- **`ARENA_BOARD_SLUG`** — the slug of your Are.na channel, found in its URL: `are.na/username/this-part-here`.

Everything else has a working default. See `.env.example` for documentation on each setting.

**For iPhone wallpapers**, also set `IPHONE_IMAGE_DIR` to a folder inside your iCloud Drive. This is where the script will write iPhone-sized images so your iPhone can read them.

The iCloud Drive path on your Mac looks like this (`~` is expanded automatically, so you
don't need to type your username):
```
~/Library/Mobile Documents/com~apple~CloudDocs/
```

The default in `.env.example` (`~/Library/Mobile Documents/com~apple~CloudDocs/sandbox/arena-wallpaper/images-iphone`)
works as-is. To use a different folder, set `IPHONE_IMAGE_DIR` to any path inside iCloud
Drive — `~/...` is fine. The script creates the folder on first run if it doesn't exist.

If `IPHONE_IMAGE_DIR` is left as the placeholder or points somewhere uncreatable, the
iPhone feature is skipped with a clear log line and the **Mac wallpaper still updates** —
a misconfigured iPhone path can no longer break the daily run.

### 4. Run manually to verify

```bash
.venv/bin/python arena_wallpaper.py && tail -n 5 arena_wallpaper.log
```

The last lines of the log should look like:

```
[2026-06-01 09:00:01] Sync complete. New images: 12
[2026-06-01 09:00:04] Set screen 0 -> some_image.jpg
[2026-06-01 09:00:04] Set screen 1 -> another_image.jpg
[2026-06-01 09:00:04] Done.
```

If you see `Done.` your wallpaper has changed and the setup is working.

### 5. Install the background task (LaunchAgent)

The LaunchAgent runs the script automatically every day at 09:00. Run the install script once:

```bash
bash install_launchagent.sh
```

This script reads your username and project path automatically, generates the LaunchAgent config, installs it, and runs the script once immediately. The last lines of the log are printed so you can confirm it worked.

You do not need to run this again. The LaunchAgent loads automatically on login from this point on.

---

## iPhone setup

After running the script at least once, open your iCloud Drive folder (`IPHONE_IMAGE_DIR` from your `.env`) and confirm that images are there. These are the wallpapers your iPhone will use.

Now set up the Shortcut that rotates them:

**In the Shortcuts app, go to Automation → + → New Automation → Personal Automation**

Set the trigger to **Time of Day**. Choose a time (e.g. 09:00). You will repeat this for as many rotation points as you want throughout the day — iOS does not support hourly repeating automations natively, so stacking multiple time triggers (e.g. every 2 hours) is the workaround. Disable **Ask Before Running** for each one.

**Add these actions to the automation:**

**Action 1 — Get Contents of Folder**
Tap the folder field and navigate to your iCloud Drive → the folder you set as `IPHONE_IMAGE_DIR` (called `images-iphone` by default).

**Action 2 — Get Random Item from List**
The folder contents from action 1 are used automatically as the list. No extra configuration needed.

**Action 3 — Set Wallpaper Photo**
The random image from action 2 is used automatically as the input. Tap the expand arrow (↓) on this action to open its settings:
- Set screen to **Lock Screen**
- Turn off **Show Preview**
- Turn off **Crop to Subject**

Save the automation. Repeat for each time trigger you want.

---

## Running manually

To trigger an immediate sync and wallpaper update from the project folder:

```bash
.venv/bin/python arena_wallpaper.py && tail -n 5 arena_wallpaper.log
```

Or use the shorthand saved in `refresh_command.txt`.

To regenerate all iPhone wallpapers (useful after changing canvas size settings):

```bash
.venv/bin/python arena_wallpaper.py --batch-iphone
```

---

## Configuration reference

All settings live in `.env`. See `.env.example` for full descriptions. Key options:

| Setting | Default | What it does |
|---|---|---|
| `WALLPAPER_SCALE` | `center` | How the image is displayed. `center` = actual size, no scaling. Also: `fill`, `fit`, `stretch`. |
| `TARGET_WIDTH` | `720` | Width in pixels of the cached copy used for display. Originals are never modified. Images narrower than this are never upscaled. |
| `PER_SCREEN_RANDOM` | `true` | Pick a different image per connected screen. |
| `RECENT_DAYS` | `7` | Number of days to avoid repeating the same image. |
| `IPHONE_CANVAS_W` / `H` | `1206` / `2622` | iPhone screen resolution. Match to your model (see below). |
| `IPHONE_IMAGE_SCALE` | `0.75` | Image width as a fraction of the canvas. Low-res images may appear smaller — this is intentional. |

**iPhone canvas sizes by model:**

| Model | Width | Height |
|---|---|---|
| iPhone 17 Pro | 1206 | 2622 |
| iPhone 16 Pro | 1206 | 2622 |
| iPhone 15 Pro | 1179 | 2556 |
| iPhone 14 Pro | 1179 | 2556 |

---

## Troubleshooting

**Wallpaper did not change after install**
Check the log: `tail -n 20 arena_wallpaper.log`. If you see `Sync complete. New images: 0` and no `Set screen` lines, the image folder may be empty. Run the script manually first to populate it.

**Are.na sync fails with a network error**
The LaunchAgent sometimes fires before macOS has established a network connection. The script handles this gracefully — the sync is skipped but the wallpaper still rotates from the local image pool. This resolves itself on the next run.

**`python3` points to the wrong Python**
Some tools (e.g. PlatformIO) add their own Python to the front of your PATH. Use the full Homebrew path explicitly: `/opt/homebrew/bin/python3`.

---

## Credits

Built by [Sjoerd Mol](https://github.com/sjoerd-mol).
Uses [Are.na](https://www.are.na) as the image source and curation layer.
Built with assistance from [Claude](https://claude.ai) (Anthropic).
