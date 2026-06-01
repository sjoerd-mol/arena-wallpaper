# arena-wallpaper

Pulls image blocks from an [Are.na](https://www.are.na) channel and uses them as rotating wallpapers on Mac and iPhone.

> **Apple ecosystem only.** This workflow is built around macOS LaunchAgents, pyobjc (macOS-native Python bindings), iCloud Drive, and iOS Shortcuts. It will not run on Windows or Linux in its current form.

---

## What it does

Two output streams, one image pool:

- **Mac** — images are downloaded to `images/`, resized copies cached in `.cache/`. A LaunchAgent fires daily at 09:00, picks a different random image per connected screen, and sets them as wallpaper via the macOS API directly (no third-party CLI needed).
- **iPhone** — each image is pre-composited onto a black canvas at the correct screen resolution and written to an iCloud Drive folder. An iOS Shortcut reads from that folder on a schedule and sets the wallpaper silently.

Low-resolution Are.na blocks appear smaller than full-width on the iPhone canvas by design — images display at their native scale rather than being stretched.

---

## Requirements

- macOS 13 or later
- Python 3.12 or later (Homebrew: `brew install python`)
- An [Are.na](https://www.are.na) account with a channel of image blocks
- iCloud Drive enabled (for the iPhone workflow)
- iPhone with iOS Shortcuts (for the iPhone workflow)

---

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/YOUR_USERNAME/arena-wallpaper.git
cd arena-wallpaper
```

**2. Create a virtual environment and install dependencies**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**3. Configure**

```bash
cp .env.example .env
```

Open `.env` and fill in:

- `ARENA_ACCESS_TOKEN` — generate one at [are.na/settings/personal-access-tokens](https://www.are.na/settings/personal-access-tokens)
- `ARENA_BOARD_SLUG` — the slug from your channel URL (`are.na/username/channel-slug`)
- `IMAGE_DIR` — absolute path to where images should be stored (e.g. `/Users/you/Documents/arena-wallpaper/images`)
- `IPHONE_IMAGE_DIR` — absolute path inside your iCloud Drive (see `.env.example` for the correct format)

All other values have sensible defaults; see `.env.example` for documentation on each.

**4. Run manually to verify**

```bash
.venv/bin/python arena_wallpaper.py && tail -n 5 arena_wallpaper.log
```

The log should end with `Done.` and show which image was set on each screen.

---

## Mac automation — LaunchAgent

The LaunchAgent runs the script daily at 09:00 without any user interaction.

**1. Create your plist from the template**

```bash
cp launchagent.plist.template com.YOUR_USERNAME.arena-wallpaper.plist
```

Open the plist and replace every occurrence of:
- `YOUR_USERNAME` — your macOS username (output of `whoami`)
- `YOUR_PROJECT_PATH` — the absolute path to the cloned repo (output of `pwd`)

**2. Install and load**

```bash
cp com.YOUR_USERNAME.arena-wallpaper.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.YOUR_USERNAME.arena-wallpaper.plist
```

**3. Trigger a manual run**

```bash
launchctl start com.YOUR_USERNAME.arena-wallpaper
```

**Network timing note:** if the LaunchAgent fires before macOS has established a network connection, the Are.na sync is skipped but the wallpaper still rotates from the local image pool. This is handled gracefully — no action needed.

---

## iPhone automation — iOS Shortcuts

The Python script writes pre-composited wallpapers to the iCloud folder you set as `IPHONE_IMAGE_DIR`. An iOS Shortcut reads from that folder and sets a random image as wallpaper.

**Canvas sizes by model:**

| Model | Width | Height |
|---|---|---|
| iPhone 17 Pro | 1206 | 2622 |
| iPhone 16 Pro | 1206 | 2622 |
| iPhone 15 Pro | 1179 | 2556 |
| iPhone 14 Pro | 1179 | 2556 |

Set `IPHONE_CANVAS_W` and `IPHONE_CANVAS_H` in `.env` to match your model.

**Shortcut setup (4 actions):**

1. **Get Contents of Folder** — set path to your iCloud Drive `images-iphone` folder
2. **Get Random Item from List** — input: output of step 1
3. **Get File** — input: Random Item
4. **Set Wallpaper Photo** — input: File, position: Centre, apply to both screens

Set this as a Personal Automation on a time trigger. iOS does not support sub-daily repeat intervals natively — the simplest workaround is to create the same automation at multiple fixed times (e.g. 09:00, 11:00, 13:00, 15:00, 17:00, 19:00). Disable "Ask Before Running" on each so they fire silently.

---

## Configuration reference

See `.env.example` for all available options with descriptions.

Key settings:

| Variable | Default | Notes |
|---|---|---|
| `WALLPAPER_SCALE` | `center` | `center` shows images at actual pixel size. Other options: `fill`, `fit`, `stretch` |
| `TARGET_WIDTH` | `720` | Width in px for the display cache. Originals in `images/` are never modified. |
| `PER_SCREEN_RANDOM` | `true` | Different image per screen when multiple displays are connected |
| `RECENT_DAYS` | `7` | Avoids repeating images shown in the last N days |
| `IPHONE_IMAGE_SCALE` | `0.75` | Image width as a fraction of the iPhone canvas. Low-res images may appear smaller. |

---

## Wallpaper scale modes

| Value | macOS label | Behaviour |
|---|---|---|
| `center` | Centre | Actual pixel size, no scaling |
| `fill` | Fill Screen | Scale to fill, crop excess |
| `fit` | Fit to Screen | Scale to fit, letterbox |
| `stretch` | Stretch to Fill | Stretch to fill, ignores aspect ratio |

---

## Running the iPhone batch manually

To regenerate all iPhone wallpapers from the current image pool (useful after changing canvas settings):

```bash
.venv/bin/python arena_wallpaper.py --batch-iphone
```

---

## Credits

Built by [Sjoerd Mol](https://github.com/sjoerd-mol).
Uses [Are.na](https://www.are.na) as the image source and curation layer.
Built with assistance from Claude (Anthropic).
