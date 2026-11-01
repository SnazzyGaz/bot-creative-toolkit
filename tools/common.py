"""Shared helpers: finding programs, fonts and colours."""
import glob, json, os, shutil, sys


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def find_blender():
    """$BLENDER, then `blender` on PATH, then ~/blender (tarball installs)."""
    env = os.environ.get("BLENDER")
    if env and os.path.isfile(env):
        return env
    p = shutil.which("blender")
    if p:
        return p
    home = os.path.expanduser("~/blender")
    for pat in (home + "/blender", home + "/*/blender", "/opt/blender*/blender"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def find_font(name=None):
    """A .ttf path for `name` (a path or a family like 'DejaVu Sans'), or a safe default."""
    if name and os.path.isfile(name):
        return name
    if shutil.which("fc-match"):
        import subprocess
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", name or "DejaVu Sans"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            if out and os.path.isfile(out):
                return out
        except Exception:
            pass
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(p):
            return p
    return None


def load_font(name=None, size=16):
    from PIL import ImageFont
    path = find_font(name)
    if path:
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def rgba(c, default=(0, 0, 0, 255)):
    """'#rgb', '#rrggbb', '#rrggbbaa', a CSS name, or [r,g,b(,a)] -> (r,g,b,a)."""
    if c is None:
        return default
    if isinstance(c, (list, tuple)):
        t = tuple(int(v) for v in c)
        return t + (255,) * (4 - len(t))
    from PIL import ImageColor
    s = str(c).strip()
    if s.lower() in ("none", "transparent"):
        return (0, 0, 0, 0)
    if s.startswith("#") and len(s) == 9:
        return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5, 7))
    return ImageColor.getcolor(s, "RGBA")


def emit(obj):
    """Print a JSON result on stdout (the only thing tools print there)."""
    print(json.dumps(obj, indent=1))
