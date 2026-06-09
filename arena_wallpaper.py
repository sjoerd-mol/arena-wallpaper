#!/usr/bin/env python3
import os, sys, random, json, time, re, subprocess, datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image
from dotenv import load_dotenv

ROOT = Path(__file__).parent.resolve()
ENV_PATH = ROOT / ".env"
IMG_DIR = ROOT / "images"
CACHE_DIR = ROOT / ".cache"
STATE_PATH = ROOT / ".state.json"
LOG_PATH = ROOT / "arena_wallpaper.log"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

def _expand(p: str) -> str:
    """Expand ~ and $VARS in a user-supplied path string."""
    return os.path.expanduser(os.path.expandvars(p))


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a") as f:
        f.write(f"[{ts}] {msg}\n")

# Values copied verbatim from .env.example — treated as "not configured".
_PLACEHOLDERS = {"", "your_personal_access_token_here", "your-channel-slug"}


def load_config():
    load_dotenv(ENV_PATH)
    token = os.getenv("ARENA_ACCESS_TOKEN", "").strip()
    slug = os.getenv("ARENA_BOARD_SLUG", "").strip()
    image_dir_env = os.getenv("IMAGE_DIR", "").strip()
    image_dir = Path(_expand(image_dir_env)) if image_dir_env else IMG_DIR
    scale = os.getenv("WALLPAPER_SCALE", "center").strip()
    per_screen_random = os.getenv("PER_SCREEN_RANDOM", "true").lower() == "true"
    target_w = int(os.getenv("TARGET_WIDTH", "480") or "0")
    recent_days = int(os.getenv("RECENT_DAYS", "7") or "0")
    iphone_dir_env = os.getenv("IPHONE_IMAGE_DIR", "").strip()
    iphone_image_dir = Path(_expand(iphone_dir_env)) if iphone_dir_env else (ROOT / "images-iphone")
    iphone_canvas_w = int(os.getenv("IPHONE_CANVAS_W", "1206") or "1206")
    iphone_canvas_h = int(os.getenv("IPHONE_CANVAS_H", "2622") or "2622")
    iphone_image_scale = float(os.getenv("IPHONE_IMAGE_SCALE", "0.75") or "0.75")
    problems = []
    if token in _PLACEHOLDERS:
        problems.append("ARENA_ACCESS_TOKEN is missing or still the .env.example placeholder")
    if slug in _PLACEHOLDERS:
        problems.append("ARENA_BOARD_SLUG is missing or still the .env.example placeholder")
    if problems:
        print("Config error in .env:\n  - " + "\n  - ".join(problems) +
              "\nEdit .env and set real values (see .env.example).", file=sys.stderr)
        sys.exit(2)
    return {
        "token": token, "slug": slug, "image_dir": image_dir,
        "scale": scale, "per_screen_random": per_screen_random,
        "target_w": target_w, "recent_days": recent_days,
        "iphone_image_dir": iphone_image_dir, "iphone_canvas_w": iphone_canvas_w,
        "iphone_canvas_h": iphone_canvas_h, "iphone_image_scale": iphone_image_scale,
    }

def ensure_dirs(*paths: Path):
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)

def iphone_dir_usable(path: Path) -> Optional[str]:
    """Return an error message if the iPhone (iCloud) output dir can't be used, else None.

    The iPhone feature is optional: a misconfigured path must never crash the run and
    stop the Mac wallpaper from updating. Catches the common 'unsubstituted placeholder'
    mistake explicitly so the log says exactly what to fix.
    """
    if "YOUR_USERNAME" in str(path):
        return ("IPHONE_IMAGE_DIR still contains the placeholder YOUR_USERNAME — "
                "edit .env and set your real iCloud path.")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"cannot create IPHONE_IMAGE_DIR ({path}): {e}"
    return None

def today_str():
    return datetime.date.today().isoformat()

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {}
    return {}

def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))

# --- Are.na via curl (avoids Cloudflare issues) ---
def curl_json(url: str, token: Optional[str]=None) -> dict:
    cmd = ["curl", "-sS", "-A", UA, "-H", "Accept: application/json"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd += [url]
    try:
        out = subprocess.check_output(cmd, text=True)
        if out.startswith("<!DOCTYPE html>"):
            raise subprocess.CalledProcessError(22, cmd, output=out)
        return json.loads(out)
    except Exception:
        sep = "&" if "?" in url else "?"
        url2 = f"{url}{sep}access_token={token or ''}"
        out2 = subprocess.check_output(["curl", "-sS", "-A", UA, "-H", "Accept: application/json", url2], text=True)
        if out2.startswith("<!DOCTYPE html>"):
            snippet = out2[:300].replace("\n"," ")
            raise RuntimeError(f"Cloudflare/403 HTML received from Are.na: {snippet}")
        return json.loads(out2)

def arena_iter_blocks(token: str, slug: str):
    page, per = 1, 100
    while True:
        data = curl_json(f"https://api.are.na/v3/channels/{slug}/contents?per={per}&page={page}", token)
        blocks = data.get("data") or []
        if not blocks:
            break
        for block in blocks:
            yield block
        meta = data.get("meta") or {}
        if not meta.get("has_more_pages", False):
            break
        page += 1

def is_image_block(block: dict) -> bool:
    return block.get("type") == "Image" and isinstance(block.get("image"), dict)

def pick_image_url(block: dict) -> Optional[Tuple[str, str]]:
    img = block.get("image") or {}
    fname = img.get("filename") or "image"
    # v3: top-level src is the original; fall back through large -> medium
    if img.get("src"):
        return img["src"], fname
    large = img.get("large") or {}
    if large.get("src"):
        return large["src"], fname
    medium = img.get("medium") or {}
    if medium.get("src"):
        return medium["src"], fname
    return None

def filename_from(block_id: int, filename: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return f"{block_id}__{base}"

def download_image(url: str, dest: Path) -> bool:
    cmd = ["curl", "-fL", "-A", UA, "-o", str(dest), url]
    subprocess.check_call(cmd)
    return True

def normalize_image(path: Path) -> Path:
    """Convert WebP to PNG and extract first frame from GIF.

    Are.na serves various image formats. WebP and GIF require normalization:
    - WebP: not universally supported as a wallpaper source; converted to PNG.
    - GIF: only the first frame is used (animated GIFs are not useful as wallpapers).

    All other formats (JPEG, PNG, TIFF, etc.) are left untouched.
    Returns the final path, which may differ from the input if conversion occurred.
    """
    try:
        with Image.open(path) as im:
            fmt = im.format
            if fmt == "GIF":
                im.seek(0)
                out = path.with_suffix(".png")
                im.convert("RGBA").convert("RGB").save(out, "PNG")
                path.unlink()
                log(f"GIF converted to PNG (first frame): {out.name}")
                return out
            elif fmt == "WEBP":
                out = path.with_suffix(".png")
                im.convert("RGB").save(out, "PNG")
                path.unlink()
                log(f"WebP converted to PNG: {out.name}")
                return out
    except Exception as e:
        log(f"Normalize failed for {path.name}: {e}")
    return path

def list_local_images(image_dir: Path) -> List[Path]:
    exts = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".gif", ".bmp", ".webp"}
    return sorted([p for p in image_dir.glob("*") if p.suffix.lower() in exts])

# Prepare centered 480px-wide temp copy; original untouched
def prepare_for_wallpaper(img: Path, target_w: int) -> Path:
    if target_w <= 0:
        return img
    ensure_dirs(CACHE_DIR)
    cache_name = f"{img.stem}__w{target_w}.png"
    outp = CACHE_DIR / cache_name
    if outp.exists():
        return outp
    try:
        with Image.open(img) as im:
            w, h = im.size
            if w <= target_w:  # never upscale
                im.convert("RGB").save(outp)
                return outp
            ratio = target_w / float(w)
            th = max(1, int(round(h * ratio)))
            im2 = im.resize((target_w, th), Image.LANCZOS)
            im2.convert("RGB").save(outp)
            return outp
    except Exception as e:
        log(f"Prep failed for {img.name}: {e}")
        return img

def prepare_iphone_wallpaper(source: Path, iphone_dir: Path, canvas_w: int,
                              canvas_h: int, img_scale: float) -> Optional[Path]:
    out = iphone_dir / (source.stem + ".jpg")
    if out.exists():
        return out
    try:
        with Image.open(source) as im:
            src_w, src_h = im.size
            scaled_w = round(canvas_w * img_scale)
            scaled_h = round(src_h * scaled_w / src_w) if src_w else canvas_h
            if scaled_h > canvas_h:
                scaled_h = canvas_h
                scaled_w = round(src_w * scaled_h / src_h) if src_h else canvas_w
            # never upscale
            scaled_w = min(scaled_w, src_w)
            scaled_h = min(scaled_h, src_h)
            im2 = im.resize((scaled_w, scaled_h), Image.LANCZOS).convert("RGB")
            canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
            x = (canvas_w - scaled_w) // 2
            y = (canvas_h - scaled_h) // 2
            canvas.paste(im2, (x, y))
            canvas.save(out, "JPEG", quality=92)
            return out
    except Exception as e:
        log(f"iPhone prep failed for {source.name}: {e}")
        return None

def _scale_options(scale: str) -> dict:
    """Map WALLPAPER_SCALE value to NSWorkspace options dict."""
    from AppKit import (
        NSWorkspaceDesktopImageScalingKey,
        NSWorkspaceDesktopImageAllowClippingKey,
        NSImageScaleProportionallyUpOrDown,
        NSImageScaleAxesIndependently,
        NSImageScaleNone,
    )
    opts = {
        "fill":    {NSWorkspaceDesktopImageScalingKey: NSImageScaleProportionallyUpOrDown,
                    NSWorkspaceDesktopImageAllowClippingKey: True},
        "fit":     {NSWorkspaceDesktopImageScalingKey: NSImageScaleProportionallyUpOrDown,
                    NSWorkspaceDesktopImageAllowClippingKey: False},
        "stretch": {NSWorkspaceDesktopImageScalingKey: NSImageScaleAxesIndependently,
                    NSWorkspaceDesktopImageAllowClippingKey: False},
        "center":  {NSWorkspaceDesktopImageScalingKey: NSImageScaleNone,
                    NSWorkspaceDesktopImageAllowClippingKey: False},
        "auto":    {NSWorkspaceDesktopImageScalingKey: NSImageScaleProportionallyUpOrDown,
                    NSWorkspaceDesktopImageAllowClippingKey: True},
    }
    return opts.get(scale, opts["center"])


def wallpaper_screens() -> List[str]:
    from AppKit import NSScreen
    screens = NSScreen.screens()
    return [str(i) for i in range(len(screens))]


def set_wallpaper_for_screen(img: Path, screen: str, scale: str):
    from AppKit import NSWorkspace, NSScreen
    from Foundation import NSURL

    options = _scale_options(scale)
    url = NSURL.fileURLWithPath_(str(img.resolve()))
    workspace = NSWorkspace.sharedWorkspace()
    all_screens = NSScreen.screens()

    if screen == "all":
        targets = list(enumerate(all_screens))
    else:
        idx = int(screen)
        if idx >= len(all_screens):
            log(f"Screen {screen} not available ({len(all_screens)} screen(s) connected)")
            return
        targets = [(idx, all_screens[idx])]

    for idx, ns_screen in targets:
        # Preserve existing options (e.g. fill color) so user-set background color survives
        current = workspace.desktopImageOptionsForScreen_(ns_screen)
        merged = dict(current) if current else {}
        merged.update(options)
        success, error = workspace.setDesktopImageURL_forScreen_options_error_(
            url, ns_screen, merged, None
        )
        if success:
            log(f"Set screen {idx} -> {img.name}")
        else:
            log(f"Failed to set screen {idx}: {error}")

def build_recent_sets(state: Dict[str, Any], recent_days: int) -> Dict[str, set]:
    recent_by_screen: Dict[str, set] = {}
    hist: Dict[str, List[Dict[str, str]]] = state.get("history", {})
    if not hist or recent_days <= 0:
        return {}
    cutoff = datetime.date.today() - datetime.timedelta(days=recent_days)
    for screen, entries in hist.items():
        s = set()
        for ent in entries:
            try:
                d = datetime.date.fromisoformat(ent.get("date","1970-01-01"))
            except Exception:
                continue
            if d >= cutoff:
                s.add(ent.get("file",""))
        recent_by_screen[screen] = s
    return recent_by_screen

def record_history(state: Dict[str, Any], screen: str, filename: str, max_entries: int = 60):
    hist = state.setdefault("history", {})
    lst = hist.setdefault(screen, [])
    lst.append({"date": today_str(), "file": filename})
    # keep it tidy
    if len(lst) > max_entries:
        del lst[:-max_entries]

def choose_nonrecent(images: List[Path], excluded: set) -> Optional[Path]:
    # try to avoid excluded; if all excluded, just return a random one
    pool = [p for p in images if p.name not in excluded]
    return random.choice(pool if pool else images) if images else None

def set_random_per_screen(images: List[Path], scale: str, target_w: int, state: dict, recent_days: int):
    screens = wallpaper_screens()
    recent = build_recent_sets(state, recent_days)

    if not images:
        log("No images available to set.")
        return

    # Shuffle the list to start fresh
    shuffled = images.copy()
    random.shuffle(shuffled)

    used_this_run = set()
    total = len(shuffled)

    for i, screen in enumerate(screens):
        excluded = recent.get(screen, set()) | used_this_run
        pick = choose_nonrecent(shuffled, excluded)

        if not pick:
            log(f"No unique pick possible for screen {screen}. Reusing random image.")
            pick = random.choice(shuffled)

        prepared = prepare_for_wallpaper(pick, target_w)
        set_wallpaper_for_screen(prepared, screen, scale)
        record_history(state, screen, pick.name)
        used_this_run.add(pick.name)
        log(f"Selected for screen {screen}: {pick.name} "
            f"(avoiding {len(excluded)} recent, {len(used_this_run)} used this run)")


def sync_and_set():
    cfg = load_config()
    # Only the local dirs are essential. The iPhone (iCloud) dir is optional and must
    # never be able to break Mac wallpaper rotation, so it's validated separately.
    ensure_dirs(cfg["image_dir"], CACHE_DIR)
    iphone_error = iphone_dir_usable(cfg["iphone_image_dir"])
    if iphone_error:
        log(f"iPhone wallpapers disabled: {iphone_error}")
    iphone_enabled = iphone_error is None

    state = load_state()
    seen = set(state.get("downloaded_ids", []))
    new_count = 0

    # Download ALL images. A network failure at boot (the LaunchAgent can fire before
    # the network is up) must not stop the wallpaper rotating off existing local images.
    try:
        for block in arena_iter_blocks(cfg["token"], cfg["slug"]):
            if not is_image_block(block):
                continue
            bid = block.get("id")
            if not bid or bid in seen:
                continue
            chosen = pick_image_url(block)
            if not chosen:
                continue
            url, fname = chosen
            dest = cfg["image_dir"] / filename_from(bid, fname)
            try:
                download_image(url, dest)
                dest = normalize_image(dest)
                seen.add(bid)
                new_count += 1
            except Exception as e:
                log(f"Download failed for block {bid}: {e}")
                dest.unlink(missing_ok=True)
        state["downloaded_ids"] = sorted(seen)
        save_state(state)
        log(f"Sync complete. New images: {new_count}")
    except Exception as e:
        log(f"Are.na sync skipped ({e}); using existing local images.")

    # Generate iPhone wallpapers for any image not yet processed (optional feature).
    if iphone_enabled:
        try:
            for img in list_local_images(cfg["image_dir"]):
                iphone_out = cfg["iphone_image_dir"] / (img.stem + ".jpg")
                if not iphone_out.exists():
                    prepare_iphone_wallpaper(img, cfg["iphone_image_dir"],
                                             cfg["iphone_canvas_w"], cfg["iphone_canvas_h"],
                                             cfg["iphone_image_scale"])
        except Exception as e:
            log(f"iPhone wallpaper generation error ({e}); continuing.")

    # Set wallpapers with no-repeat
    imgs = list_local_images(cfg["image_dir"])
    if cfg["per_screen_random"]:
        set_random_per_screen(imgs, cfg["scale"], cfg["target_w"], state, cfg["recent_days"])
    else:
        if imgs:
            picked = choose_nonrecent(imgs, set())
            prepared = prepare_for_wallpaper(picked, cfg["target_w"])
            set_wallpaper_for_screen(prepared, "all", cfg["scale"])
            record_history(state, "all", picked.name)
            log(f"Selected for all screens: {picked.name}")
    save_state(state)
    log("Done.")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--batch-iphone":
        cfg = load_config()
        ensure_dirs(cfg["image_dir"], CACHE_DIR)
        iphone_error = iphone_dir_usable(cfg["iphone_image_dir"])
        if iphone_error:
            print(f"Cannot batch iPhone wallpapers: {iphone_error}", file=sys.stderr)
            sys.exit(2)
        imgs = list_local_images(cfg["image_dir"])
        total = len(imgs)
        processed = 0
        for img in imgs:
            result = prepare_iphone_wallpaper(img, cfg["iphone_image_dir"],
                                              cfg["iphone_canvas_w"], cfg["iphone_canvas_h"],
                                              cfg["iphone_image_scale"])
            if result:
                processed += 1
        msg = f"iPhone batch: {processed} / {total} processed"
        log(msg)
        print(msg)
    elif args and args[0] == "--dry-run":
        # Fetch v3 blocks and print parsed data without writing any files.
        cfg = load_config()
        print(f"Dry run — fetching blocks from Are.na channel: {cfg['slug']}")
        count = 0
        image_count = 0
        for block in arena_iter_blocks(cfg["token"], cfg["slug"]):
            count += 1
            bid = block.get("id")
            cls = block.get("class")
            if is_image_block(block):
                image_count += 1
                chosen = pick_image_url(block)
                url, fname = chosen if chosen else ("(no url)", "(no filename)")
                print(f"  [{count}] Image block id={bid} file={fname} url={url}")
            else:
                print(f"  [{count}] Non-image block id={bid} class={cls}")
        print(f"\nTotal blocks: {count}  Image blocks: {image_count}")
        print("Dry run complete — no files written.")
    else:
        sync_and_set()
