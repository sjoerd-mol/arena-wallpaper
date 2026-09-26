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


_LOG_MAX_BYTES = 1_000_000  # rotate arena_wallpaper.log past ~1 MB (keep one .1 backup)

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > _LOG_MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_name(LOG_PATH.name + ".1"))
    except OSError:
        pass
    with LOG_PATH.open("a") as f:
        f.write(f"[{ts}] {msg}\n")

# Values copied verbatim from .env.example — treated as "not configured".
_PLACEHOLDERS = {"", "your_personal_access_token_here", "your-channel-slug"}


def _env_number(name: str, default, cast=int, if_empty=None):
    """Read a numeric setting; a typo (e.g. '720px') falls back to the default
    instead of crashing the unattended run. `if_empty` is used when the variable is
    set but blank (e.g. 'TARGET_WIDTH=' means 0, i.e. off)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default if if_empty is None else if_empty
    try:
        return cast(raw)
    except ValueError:
        msg = f"{name}={raw!r} is not a valid number; using default {default}."
        log(f"Config warning: {msg}")
        print(f"Config warning: {msg}", file=sys.stderr)
        return default


def _parse_hex_color(raw: str) -> Optional[Tuple[float, float, float]]:
    """'#4A7061' or '4A7061' -> (r, g, b) in 0..1; None if empty or invalid."""
    s = raw.strip().lstrip("#")
    if not s:
        return None
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        msg = f"WALLPAPER_FILL_COLOR={raw!r} is not a #RRGGBB hex color; ignoring it."
        log(f"Config warning: {msg}")
        print(f"Config warning: {msg}", file=sys.stderr)
        return None
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def load_config():
    load_dotenv(ENV_PATH, override=True)
    token = os.getenv("ARENA_ACCESS_TOKEN", "").strip()
    slug = os.getenv("ARENA_BOARD_SLUG", "").strip()
    image_dir_env = os.getenv("IMAGE_DIR", "").strip()
    image_dir = Path(_expand(image_dir_env)) if image_dir_env else IMG_DIR
    scale = os.getenv("WALLPAPER_SCALE", "center").strip()
    fill_color = _parse_hex_color(os.getenv("WALLPAPER_FILL_COLOR", ""))
    per_screen_random = os.getenv("PER_SCREEN_RANDOM", "true").lower() == "true"
    target_w = _env_number("TARGET_WIDTH", 720, if_empty=0)
    recent_days = _env_number("RECENT_DAYS", 7, if_empty=0)
    iphone_dir_env = os.getenv("IPHONE_IMAGE_DIR", "").strip()
    iphone_image_dir = Path(_expand(iphone_dir_env)) if iphone_dir_env else (ROOT / "images-iphone")
    iphone_canvas_w = _env_number("IPHONE_CANVAS_W", 1206)
    iphone_canvas_h = _env_number("IPHONE_CANVAS_H", 2622)
    iphone_image_scale = _env_number("IPHONE_IMAGE_SCALE", 0.75, float)
    ntfy_url = os.getenv("NTFY_URL", "").strip()
    ntfy_token = os.getenv("NTFY_TOKEN", "").strip()
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
        "scale": scale, "fill_color": fill_color, "per_screen_random": per_screen_random,
        "target_w": target_w, "recent_days": recent_days,
        "iphone_image_dir": iphone_image_dir, "iphone_canvas_w": iphone_canvas_w,
        "iphone_canvas_h": iphone_canvas_h, "iphone_image_scale": iphone_image_scale,
        "ntfy_url": ntfy_url, "ntfy_token": ntfy_token,
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
    # Atomic write: a kill mid-write must never corrupt state (a truncated file would
    # force a full re-download and wipe the no-repeat history).
    tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_PATH)

def notify(cfg: dict, title: str, message: str, priority: str = "default", tags: str = ""):
    """Send an ntfy push if NTFY_URL is configured; a no-op otherwise.

    Uses curl (no extra dependency) and never raises — a notification failure must
    not affect the wallpaper run.
    """
    url = cfg.get("ntfy_url")
    if not url:
        return
    cmd = ["curl", "-sS", "--connect-timeout", "10", "--max-time", "30",
           "-H", f"Title: {title}"]
    if priority:
        cmd += ["-H", f"Priority: {priority}"]
    if tags:
        cmd += ["-H", f"Tags: {tags}"]
    if cfg.get("ntfy_token"):
        cmd += ["-H", f"Authorization: Bearer {cfg['ntfy_token']}"]
    cmd += ["-d", message, url]
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"ntfy notification failed: {e}")

# --- Are.na via curl (avoids Cloudflare issues) ---
class ArenaAPIError(RuntimeError):
    """Are.na answered, but with an error (bad token, unknown channel, ...).

    Without -f, curl exits 0 on a 401/404 and prints a JSON error body. That body has
    no 'data' list, and used to look exactly like an empty channel: the run reported
    'Sync complete' and nobody noticed the token or slug was wrong.
    """
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code

def _curl_json_once(url: str, token: Optional[str]) -> dict:
    cmd = ["curl", "-sS", "--connect-timeout", "15", "--max-time", "120",
           "-A", UA, "-H", "Accept: application/json"]
    if token:
        # Token stays in the Authorization header — never placed in the URL.
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd += [url]
    out = subprocess.check_output(cmd, text=True)
    head = out.lstrip().lower()
    if head.startswith("<!doctype html") or head.startswith("<html"):
        raise RuntimeError(f"HTML received from Are.na (Cloudflare/403): {out[:200].strip()}")
    data = json.loads(out)
    if not isinstance(data, dict) or "error" in data or not isinstance(data.get("data"), list):
        err = data if isinstance(data, dict) else {}
        code = err.get("code") if isinstance(err.get("code"), int) else None
        detail = (err.get("details") or {}).get("message") if isinstance(err.get("details"), dict) else None
        msg = err.get("error") or "unexpected response (no 'data' list)"
        raise ArenaAPIError(f"Are.na API error{f' {code}' if code else ''}: {msg}"
                            f"{f' ({detail})' if detail else ''}", code)
    return data

def curl_json(url: str, token: Optional[str]=None) -> dict:
    # One retry for transient failures (network blip, timeout, brief 403). The retry
    # uses the same header-based request — the token is never moved into the URL.
    try:
        return _curl_json_once(url, token)
    except ArenaAPIError as e:
        if e.code in (401, 403, 404):
            raise  # wrong token or slug: retrying won't help
        log(f"Are.na request failed ({e}); retrying once.")
        return _curl_json_once(url, token)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError, RuntimeError) as e:
        log(f"Are.na request failed ({e}); retrying once.")
        return _curl_json_once(url, token)

def arena_iter_blocks(token: str, slug: str, report: Optional[dict] = None):
    """Yield every block of the channel, page by page.

    If `report` is given, it is filled in: 'complete' is True only when paging ended
    normally and the number of blocks matches the API's total_count. The prune step
    relies on this, so a page that comes back short can never delete local images.
    """
    page, per = 1, 100
    seen = 0
    total_count = None
    complete = False
    while True:
        data = curl_json(f"https://api.are.na/v3/channels/{slug}/contents?per={per}&page={page}", token)
        meta = data.get("meta") or {}
        if total_count is None and isinstance(meta.get("total_count"), int):
            total_count = meta["total_count"]
        blocks = data.get("data") or []
        for block in blocks:
            seen += 1
            yield block
        if not meta.get("has_more_pages", False):
            complete = total_count is None or seen == total_count
            break
        if not blocks:
            break  # API claims more pages but sent none: treat as incomplete
        page += 1
    if report is not None:
        report.update(complete=complete, seen=seen, total_count=total_count)

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

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".gif", ".bmp", ".webp"}
_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "image/heic": ".heic", "image/tiff": ".tiff", "image/bmp": ".bmp",
}

def filename_from(block_id: int, filename: str, content_type: str = "") -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    # Without a known image extension, list_local_images would never see the file,
    # while its id is still marked as downloaded: it would be silently lost.
    if Path(base).suffix.lower() not in IMAGE_EXTS:
        base += _EXT_BY_CONTENT_TYPE.get((content_type or "").lower(), ".jpg")
    return f"{block_id}__{base}"

def download_image(url: str, dest: Path) -> bool:
    cmd = ["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "120",
           "-A", UA, "-o", str(dest), url]
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
    return sorted([p for p in image_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS])

_BID_PREFIX = re.compile(r"^(\d+)__")

class PruneRefused(RuntimeError):
    pass

def prune_removed(image_dir: Path, cache_dir: Path, iphone_dir: Path, current_ids: set,
                  max_share: float = 0.25) -> int:
    """Delete local files whose Are.na block id is no longer present on the channel.

    Only ever touches files named '<digits>__...' (the convention from filename_from),
    so unrelated files are never at risk. The caller must invoke this only after a
    clean, complete sync with a non-empty current_ids set.

    As a last safety net, refuses (PruneRefused) when more than `max_share` of the
    local originals would go at once (with a floor of 5 files): that looks like a bad
    API response, not a curator removing a few blocks.
    """
    doomed: List[Path] = []
    doomed_originals = originals = 0
    for d in (image_dir, cache_dir, iphone_dir):
        if not d or not d.exists():
            continue
        for f in d.glob("*"):
            if not f.is_file():
                continue
            m = _BID_PREFIX.match(f.name)
            if not m:
                continue
            if d is image_dir:
                originals += 1
            if int(m.group(1)) not in current_ids:
                doomed.append(f)
                if d is image_dir:
                    doomed_originals += 1
    if doomed_originals > max(5, int(originals * max_share)):
        raise PruneRefused(f"would delete {doomed_originals} of {originals} local images; "
                           f"skipped as a safety measure")
    removed = 0
    for f in doomed:
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed

# Prepare a centered, width-capped display copy (TARGET_WIDTH); original untouched
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


def _color_to_rgba(color) -> Optional[List[float]]:
    from AppKit import NSColorSpace
    try:
        c = color.colorUsingColorSpace_(NSColorSpace.genericRGBColorSpace())
        return [c.redComponent(), c.greenComponent(), c.blueComponent(), c.alphaComponent()]
    except Exception:
        return None


def set_wallpaper_for_screen(img: Path, screen: str, scale: str,
                             fill_color: Optional[Tuple[float, float, float]] = None,
                             known_colors: Optional[Dict[str, List[float]]] = None):
    """Set `img` on one screen (index as string) or on "all".

    Fill color, in order of preference:
      1. `fill_color` (WALLPAPER_FILL_COLOR in .env);
      2. the color macOS reports for the screen right now (kept as-is);
      3. the last color seen for this display in an earlier run (`known_colors`,
         keyed by display name, persisted in .state.json).
    macOS keeps the color per Space and per display, and does not always report it:
    for a few seconds after a change, and apparently for a Space/display pair it has
    not stored yet. Passing no color makes macOS fall back to its default blue.
    """
    from AppKit import NSWorkspace, NSScreen, NSColor, NSWorkspaceDesktopImageFillColorKey
    from Foundation import NSURL

    options = dict(_scale_options(scale))
    if fill_color:
        options[NSWorkspaceDesktopImageFillColorKey] = \
            NSColor.colorWithCalibratedRed_green_blue_alpha_(*fill_color, 1.0)
    url = NSURL.fileURLWithPath_(str(img.resolve()))
    workspace = NSWorkspace.sharedWorkspace()
    all_screens = NSScreen.screens()

    if screen == "all":
        targets = list(enumerate(all_screens))
    else:
        idx = int(screen)
        if idx >= len(all_screens):
            log(f"Screen {screen} not available ({len(all_screens)} screen(s) connected)")
            return False
        targets = [(idx, all_screens[idx])]

    ok = True
    for idx, ns_screen in targets:
        name = str(ns_screen.localizedName())
        # Preserve existing options (e.g. fill color) so user-set background color survives
        current = workspace.desktopImageOptionsForScreen_(ns_screen)
        merged = dict(current) if current else {}
        reported = merged.get(NSWorkspaceDesktopImageFillColorKey)
        if reported is not None and known_colors is not None:
            rgba = _color_to_rgba(reported)
            if rgba:
                known_colors[name] = rgba
        elif reported is None and not fill_color:
            remembered = (known_colors or {}).get(name)
            if remembered:
                merged[NSWorkspaceDesktopImageFillColorKey] = \
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(*remembered)
                log(f"Screen {idx} ({name}): macOS reported no fill color; "
                    f"reusing the last known one.")
            else:
                log(f"Screen {idx} ({name}): macOS reported no fill color, so it will fall "
                    f"back to its default. Set WALLPAPER_FILL_COLOR in .env to pin a color.")
        merged.update(options)
        success, error = workspace.setDesktopImageURL_forScreen_options_error_(
            url, ns_screen, merged, None
        )
        if success:
            log(f"Set screen {idx} -> {img.name}")
        else:
            log(f"Failed to set screen {idx}: {error}")
            ok = False
    return ok

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

def set_random_per_screen(images: List[Path], scale: str, target_w: int, state: dict, recent_days: int,
                          fill_color: Optional[Tuple[float, float, float]] = None):
    screens = wallpaper_screens()
    recent = build_recent_sets(state, recent_days)

    if not images:
        log("No images available to set.")
        return 0, 0

    # Shuffle the list to start fresh
    shuffled = images.copy()
    random.shuffle(shuffled)

    used_this_run = set()
    total = len(shuffled)
    set_ok = set_fail = 0

    for i, screen in enumerate(screens):
        excluded = recent.get(screen, set()) | used_this_run
        pick = choose_nonrecent(shuffled, excluded)

        if not pick:
            log(f"No unique pick possible for screen {screen}. Reusing random image.")
            pick = random.choice(shuffled)

        prepared = prepare_for_wallpaper(pick, target_w)
        if set_wallpaper_for_screen(prepared, screen, scale, fill_color,
                                    state.setdefault("fill_colors", {})):
            set_ok += 1
        else:
            set_fail += 1
        record_history(state, screen, pick.name)
        used_this_run.add(pick.name)
        log(f"Selected for screen {screen}: {pick.name} "
            f"(avoiding {len(excluded)} recent, {len(used_this_run)} used this run)")
    return set_ok, set_fail


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
    current_ids: set = set()
    total_blocks = image_blocks = 0
    sync_ok = False
    paging: dict = {}
    warnings: list = []   # soft issues — reported quietly in the daily summary
    errors: list = []     # hard failures — trigger a high-priority alert

    # Download ALL images. A network failure at boot (the LaunchAgent can fire before
    # the network is up) must not stop the wallpaper rotating off existing local images.
    try:
        for block in arena_iter_blocks(cfg["token"], cfg["slug"], paging):
            total_blocks += 1
            if not is_image_block(block):
                continue
            image_blocks += 1
            bid = block.get("id")
            if not bid:
                continue
            current_ids.add(bid)
            if bid in seen:
                continue
            chosen = pick_image_url(block)
            if not chosen:
                continue
            url, fname = chosen
            content_type = (block.get("image") or {}).get("content_type", "")
            dest = cfg["image_dir"] / filename_from(bid, fname, content_type)
            try:
                download_image(url, dest)
                dest = normalize_image(dest)
                seen.add(bid)
                new_count += 1
            except Exception as e:
                log(f"Download failed for block {bid}: {e}")
                dest.unlink(missing_ok=True)
        sync_ok = True
        if total_blocks and image_blocks == 0:
            msg = (f"channel returned {total_blocks} blocks but 0 image blocks — "
                   f"Are.na may have changed its API shape (expected type == 'Image').")
            log(f"Warning: {msg}")
            warnings.append(msg)
        # Forget ids no longer present on the channel.
        if current_ids:
            seen &= current_ids
        state["downloaded_ids"] = sorted(seen)
        save_state(state)
        log(f"Sync complete. New images: {new_count}")
    except ArenaAPIError as e:
        # Wrong token or slug: the agent keeps rotating old images forever unless told.
        log(f"Are.na sync failed: {e}")
        errors.append(f"{e}. Check ARENA_ACCESS_TOKEN and ARENA_BOARD_SLUG in .env.")
    except Exception as e:
        log(f"Are.na sync skipped ({e}); using existing local images.")
        warnings.append(f"Are.na sync skipped ({type(e).__name__}); used existing images.")

    # Prune local files for blocks removed from the channel — only after a clean,
    # complete sync that actually returned images, so a transient empty response can
    # never wipe the whole library.
    if sync_ok and current_ids and not paging.get("complete"):
        msg = (f"Prune skipped: channel listing looks incomplete "
               f"({paging.get('seen')} of {paging.get('total_count')} blocks received).")
        log(msg)
        warnings.append(msg)
    elif sync_ok and current_ids:
        try:
            n = prune_removed(cfg["image_dir"], CACHE_DIR, cfg["iphone_image_dir"], current_ids)
            if n:
                log(f"Pruned {n} file(s) for blocks no longer on the channel.")
        except PruneRefused as e:
            log(f"Prune skipped: {e}.")
            warnings.append(f"Prune skipped: {e}.")
        except Exception as e:
            log(f"Prune skipped ({e}).")

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
    set_ok = set_fail = 0
    if not imgs:
        errors.append("No local images available to set as wallpaper.")
    elif cfg["per_screen_random"]:
        set_ok, set_fail = set_random_per_screen(imgs, cfg["scale"], cfg["target_w"], state,
                                                 cfg["recent_days"], cfg["fill_color"])
    else:
        recent_all = build_recent_sets(state, cfg["recent_days"]).get("all", set())
        picked = choose_nonrecent(imgs, recent_all)
        prepared = prepare_for_wallpaper(picked, cfg["target_w"])
        if set_wallpaper_for_screen(prepared, "all", cfg["scale"], cfg["fill_color"],
                                    state.setdefault("fill_colors", {})):
            set_ok = 1
        else:
            set_fail = 1
        record_history(state, "all", picked.name)
        log(f"Selected for all screens: {picked.name}")
    if set_fail:
        errors.append(f"{set_fail} screen(s) failed to set wallpaper.")
    save_state(state)
    log("Done.")

    # --- ntfy notifications (no-op unless NTFY_URL is set in .env) ---
    # Hard failures alert immediately; a clean run sends one quiet summary per day
    # (so the extra RunAtLoad runs on login don't spam you).
    if errors:
        body = "\n".join(errors + warnings) + f"\n(new images: {new_count}, screens set: {set_ok})"
        notify(cfg, "arena-wallpaper: problem", body, priority="high")
    else:
        today = today_str()
        if state.get("last_summary_date") != today:
            summary = f"Wallpaper updated on {set_ok} screen(s), {new_count} new image(s)."
            if warnings:
                summary += "\n" + "\n".join(warnings)
            notify(cfg, "arena-wallpaper: daily summary", summary, priority="low")
            state["last_summary_date"] = today
            save_state(state)

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
        paging: dict = {}
        try:
            for block in arena_iter_blocks(cfg["token"], cfg["slug"], paging):
                count += 1
                bid = block.get("id")
                if is_image_block(block):
                    image_count += 1
                    chosen = pick_image_url(block)
                    url, fname = chosen if chosen else ("(no url)", "(no filename)")
                    print(f"  [{count}] Image block id={bid} file={fname} url={url}")
                else:
                    print(f"  [{count}] Non-image block id={bid} type={block.get('type')}")
        except ArenaAPIError as e:
            print(f"{e}. Check ARENA_ACCESS_TOKEN and ARENA_BOARD_SLUG in .env.", file=sys.stderr)
            sys.exit(1)
        print(f"\nTotal blocks: {count}  Image blocks: {image_count}  "
              f"(API total_count: {paging.get('total_count')}, complete: {paging.get('complete')})")
        print("Dry run complete — no files written.")
    else:
        sync_and_set()
