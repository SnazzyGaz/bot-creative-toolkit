"""Runs inside FontForge's Python (`fontforge -lang=py -script font_ff.py JOB.json`). Called by font.py."""
import json, os, sys
import fontforge, psMat

job = json.load(open(sys.argv[1]))
out = {"ok": True}

DESC = set("gjpqy")


def char_for(stem):
    """file stem -> (codepoint, glyph name) or None. 'A', 'uni0041', 'u0041', 'U+0041', 'exclam', '0041'."""
    if len(stem) == 1: return ord(stem), fontforge.nameFromUnicode(ord(stem))
    s = stem
    for pre in ("uni", "U+", "u+", "u"):
        if s.startswith(pre) and all(c in "0123456789abcdefABCDEF" for c in s[len(pre):]) and 4 <= len(s) - len(pre) <= 6:
            cp = int(s[len(pre):], 16); return cp, fontforge.nameFromUnicode(cp)
    if stem.endswith(("_upper", "-upper")) and len(stem.split("_")[0].split("-")[0]) == 1:   # a_upper.svg for case-blind disks
        c = stem[0].upper(); return ord(c), c
    cp = fontforge.unicodeFromName(stem)
    return (cp, stem) if cp >= 0 else None


def build(j):
    f = fontforge.font()
    f.em = j["em"]; f.ascent = int(j["em"] * 0.8); f.descent = j["em"] - f.ascent
    f.fontname = j["name"].replace(" ", ""); f.familyname = j["name"]; f.fullname = j["name"]
    f.copyright = j.get("copyright", ""); f.version = j.get("version", "1.000")
    f.encoding = "UnicodeFull"
    files = sorted(x for x in os.listdir(j["svgdir"]) if x.lower().endswith(".svg"))
    used, skipped = [], []
    for fn in files:
        m = char_for(os.path.splitext(fn)[0])
        if not m: skipped.append(fn); continue
        cp, name = m
        g = f.createChar(cp, name)
        g.importOutlines(os.path.join(j["svgdir"], fn))
        if g.boundingBox() == (0, 0, 0, 0): skipped.append(fn + " (empty)"); g.clear(); continue
        used.append((cp, g, fn))
    if not used: raise SystemExit("no usable SVG glyphs (name files A.svg, b.svg, uni0041.svg, exclam.svg ...)")
    cap = j["cap_height"] * j["em"]
    if j["fit"]:
        ref = [g.boundingBox() for cp, g, fn in used if not chr(cp) in DESC] or [g.boundingBox() for _, g, _ in used]
        tallest = max(b[3] - b[1] for b in ref)
        sc = cap / tallest
        for cp, g, fn in used:
            g.transform(psMat.scale(sc))
            b = g.boundingBox()
            drop = (b[3] - b[1]) * 0.25 if chr(cp) in DESC else 0
            g.transform(psMat.translate(0, -b[1] - drop))
    for cp, g, fn in used:
        g.removeOverlap(); g.correctDirection(); g.addExtrema()
        if j["simplify"]: g.simplify(j["simplify"])
        g.round()
        b = g.boundingBox()
        g.transform(psMat.translate(j["bearing"] - b[0], 0))
        g.width = int(round(b[2] - b[0] + 2 * j["bearing"]))
    if 32 not in [cp for cp, _, _ in used]:
        sp = f.createChar(32, "space"); sp.width = int(j["em"] * j["space"])
    # FontForge treats these as offsets unless the *_add flags are off; set real values so line height = em
    for k in ("os2_typoascent", "os2_typodescent", "hhea_ascent", "hhea_descent", "os2_winascent", "os2_windescent"):
        setattr(f, k + "_add", False)
    f.os2_typoascent = f.ascent; f.os2_typodescent = -f.descent; f.os2_typolinegap = 0
    f.hhea_ascent = f.ascent; f.hhea_descent = -f.descent; f.hhea_linegap = 0
    f.os2_winascent = f.ascent; f.os2_windescent = f.descent
    f.os2_use_typo_metrics = True
    if j["hint"]: f.selection.all(); f.autoHint()
    f.generate(j["out"])
    out.update({"out": j["out"], "glyphs": len(used) + (0 if 32 in [cp for cp, _, _ in used] else 1),
                "chars": "".join(chr(cp) for cp, _, _ in sorted(used, key=lambda x: x[0])), "skipped": skipped})


def info(j):
    f = fontforge.open(j["input"])
    chars = sorted(g.unicode for g in f.glyphs() if g.unicode >= 0)
    out.update({"file": j["input"], "family": f.familyname, "fontname": f.fontname, "em": f.em, "ascent": f.ascent,
                "descent": f.descent, "glyph_count": len(list(f.glyphs())),
                "chars": "".join(chr(c) for c in chars if c >= 32 and c != 127)[:2000], "version": f.version})


def convert(j):
    f = fontforge.open(j["input"])
    if j.get("name"): f.fontname = j["name"].replace(" ", ""); f.familyname = j["name"]; f.fullname = j["name"]
    f.generate(j["out"])
    out.update({"out": j["out"]})


try:
    {"build": build, "info": info, "convert": convert}[job["cmd"]](job)
except BaseException as e:
    out = {"ok": False, "error": str(e) or e.__class__.__name__}
json.dump(out, open(job["result"], "w"))
