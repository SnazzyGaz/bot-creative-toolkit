"""bct audio: make, edit and look at sound with SoX. Output format comes from the file extension
(.wav .flac .ogg .mp3 .aiff). Every command prints JSON with the result's duration and peak level.

Make
  tone OUT --freq 440 [--to 880] [--dur 1] [--wave sine|square|triangle|sawtooth|pluck] [--vol 0.5]
        one tone; --to sweeps the pitch
  noise OUT [--color white|pink|brown] [--dur 1] [--vol 0.3]
  synth OUT --notes "C5/8 E5/8 G5/4 R/8 C6+E6+G6/2" [--bpm 120] [--wave pluck] [--vol 0.7] [--reverb 30]
        a tune. Each note is NAME[+NAME...]/LENGTH: names like C4, F#5, Bb3 or a number in Hz, R for a rest,
        '+' for a chord; length 1 = whole note, 4 = quarter, 8 = eighth (add . for dotted: 4.).
        Notes get a short attack and release so they don't click.
Edit
  trim IN -o OUT --start 0.5 [--end 2.0 | --dur 1.5]
  fade IN -o OUT [--in 0.05] [--fade-out 0.3]
  norm IN -o OUT [--db -1]            loudest peak to this level
  concat A B ... -o OUT [--gap 0.2]   one after another
  mix A B ... -o OUT [--vol 1,0.5]    on top of each other
  fx IN -o OUT [--reverb 40] [--echo 0.3] [--pitch 300] [--tempo 1.2] [--speed 0.8] [--lowpass 3000]
        [--highpass 200] [--bass 6] [--treble -3] [--gain -3] [-- any sox effects ...]
        --pitch is in cents (100 = a semitone, keeps length); --speed changes pitch and length together
See
  wave IN -o OUT.png [--width 1200] [--height 300]     waveform picture with a time axis
  spectrogram IN -o OUT.png [--width 1200] [--height 400] [--title T]   frequency over time
  probe IN        duration, rate, channels, peak and RMS level (dBFS), clipping, silence
"""
import argparse, json, math, os, re, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit


def sox(*args, what="SoX"):
    exe = shutil.which("sox")
    if not exe: die("sox not found. Run setup.sh")
    p = subprocess.run([exe, "-V1"] + [str(a) for a in args], capture_output=True, text=True)
    if p.returncode != 0: die(f"{what} failed: {p.stderr.strip()[-400:]}", 1)
    return p


def probe(path):
    exe = shutil.which("soxi")
    rate = chans = dur = None
    if exe:
        q = lambda f: subprocess.run([exe, f, path], capture_output=True, text=True).stdout.strip()
        rate, chans, dur = q("-r"), q("-c"), q("-D")
    st = sox(path, "-n", "stats").stderr
    val = lambda k: (re.search(rf"^{re.escape(k)}\s+(\S+)", st, re.M) or [None, None])[1]
    num = lambda v: None if v in (None, "-inf", "inf") else float(v)
    pk, rms = num(val("Pk lev dB")), num(val("RMS lev dB"))
    lo, hi = num(val("Min level")), num(val("Max level"))
    res = {"file": os.path.abspath(path), "seconds": round(float(dur), 3) if dur else num(val("Length s")),
           "rate": int(rate) if rate else None, "channels": int(chans) if chans else None,
           "peak_db": pk, "rms_db": rms, "peak": round(max(abs(lo or 0), abs(hi or 0)), 4),
           "silent": pk is None or pk < -60, "clipped": (max(abs(lo or 0), abs(hi or 0)) >= 0.999)}
    return res


def done(out, extra=None):
    r = probe(out); r["out"] = r.pop("file")
    if extra: r.update(extra)
    emit(r)


def outdir(out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)


NOTE = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


def hz(name):
    if re.fullmatch(r"\d+(\.\d+)?", name): return float(name)
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", name)
    if not m: die(f"bad note {name!r}: use C4, F#5, Bb3 or a number in Hz")
    n = NOTE[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)] + 12 * (int(m.group(3)) - 4)
    return round(440 * 2 ** (n / 12), 3)


def cmd_tone(a):
    outdir(a.out)
    f = f"{a.freq}" + (f"-{a.to}" if a.to else "")
    sox("-n", "-r", a.rate, "-c", 1, a.out, "synth", a.dur, a.wave, f, "vol", a.vol, "fade", "q", 0.005, a.dur, 0.01)
    done(a.out, {"freq": a.freq, "to": a.to, "wave": a.wave})


def cmd_noise(a):
    outdir(a.out)
    sox("-n", "-r", a.rate, "-c", 1, a.out, "synth", a.dur, a.color + "noise", "vol", a.vol)
    done(a.out, {"color": a.color})


def cmd_synth(a):
    outdir(a.out)
    beat = 60.0 / a.bpm  # a quarter note
    tmp = tempfile.mkdtemp(prefix="bct_audio_")
    parts, total = [], 0.0
    for k, tok in enumerate(a.notes.split()):
        name, _, ln = tok.partition("/")
        ln = ln or "4"
        dotted = ln.endswith("."); ln = ln.rstrip(".")
        try: d = 4.0 / float(ln) * beat * (1.5 if dotted else 1)
        except ValueError: die(f"bad length in {tok!r}")
        p = os.path.join(tmp, f"n{k:04d}.wav")
        if name.upper() == "R":
            sox("-n", "-r", a.rate, "-c", 1, p, "trim", 0, round(d, 4))
        else:
            freqs = [hz(n) for n in name.split("+")]
            waves = []
            for f in freqs: waves += [a.wave, f]
            rel = min(0.08, d / 3)
            eff = ["synth", round(d, 4)] + waves + ["fade", "q", 0.006, round(d, 4), rel]
            if len(freqs) == 1:
                sox("-n", "-r", a.rate, "-c", 1, p, *eff)
            else:   # synth puts each wave on its own channel; then mix them down to one
                pm = p[:-4] + "_chord.wav"
                sox("-n", "-r", a.rate, "-c", len(freqs), pm, *eff)
                sox(pm, "-c", 1, p, "remix", "-", "gain", "-n", -1)   # as loud as a single note
        parts.append(p); total += d
    out_tmp = os.path.join(tmp, "all.wav")
    sox(*parts, out_tmp)
    eff = []
    if a.reverb: eff += ["pad", 0, 0.5, "reverb", a.reverb]   # pad first so the tail has room
    eff += ["gain", "-n", round(20 * math.log10(a.vol), 2)]
    sox(out_tmp, a.out, *eff)
    shutil.rmtree(tmp, ignore_errors=True)
    done(a.out, {"notes": len(parts), "bpm": a.bpm, "wave": a.wave})


def cmd_trim(a):
    outdir(a.out)
    if a.end is not None and a.dur is not None: die("give --end or --dur, not both")
    length = a.dur if a.dur is not None else (a.end - a.start if a.end is not None else None)
    if length is not None and length <= 0: die("--end must be after --start")
    sox(a.input, a.out, "trim", a.start, *([length] if length is not None else []))
    done(a.out)


def cmd_fade(a):
    outdir(a.out)
    d = probe(a.input)["seconds"]
    sox(a.input, a.out, "fade", "q", a.fade_in, d, a.fade_out)
    done(a.out)


def cmd_norm(a):
    outdir(a.out); sox(a.input, a.out, "gain", "-n", a.db); done(a.out)


def same_format(files, tmp):
    """resample/remix inputs to the first one's rate and channels so sox can join them."""
    r0 = probe(files[0]); out = []
    for k, f in enumerate(files):
        p = os.path.join(tmp, f"in{k}.wav")
        sox(f, "-r", r0["rate"], "-c", r0["channels"], p); out.append(p)
    return out, r0


def cmd_concat(a):
    outdir(a.out); tmp = tempfile.mkdtemp(prefix="bct_audio_")
    files, r0 = same_format(a.inputs, tmp)
    if a.gap:
        g = os.path.join(tmp, "gap.wav"); sox("-n", "-r", r0["rate"], "-c", r0["channels"], g, "trim", 0, a.gap)
        files = sum(([f, g] for f in files), [])[:-1]
    sox(*files, a.out); shutil.rmtree(tmp, ignore_errors=True); done(a.out, {"parts": len(a.inputs)})


def cmd_mix(a):
    outdir(a.out); tmp = tempfile.mkdtemp(prefix="bct_audio_")
    files, _ = same_format(a.inputs, tmp)
    vols = [float(v) for v in a.vol.split(",")] if a.vol else [1.0] * len(files)
    if len(vols) != len(files): die("--vol needs one value per input")
    args = ["-m"]
    for v, f in zip(vols, files): args += ["-v", v, f]
    sox(*args, a.out); shutil.rmtree(tmp, ignore_errors=True)
    done(a.out, {"parts": len(a.inputs)})


def cmd_fx(a):
    outdir(a.out)
    eff = []
    if a.highpass: eff += ["highpass", a.highpass]
    if a.lowpass: eff += ["lowpass", a.lowpass]
    if a.bass: eff += ["bass", a.bass]
    if a.treble: eff += ["treble", a.treble]
    if a.pitch: eff += ["pitch", a.pitch]
    if a.tempo: eff += ["tempo", a.tempo]
    if a.speed: eff += ["speed", a.speed]
    if a.echo: eff += ["echo", 0.8, 0.88, 120, a.echo, 260, a.echo * 0.5]
    if a.reverb: eff += ["reverb", a.reverb]
    if a.gain: eff += ["gain", a.gain]
    eff += a.extra
    if not eff: die("no effects given")
    sox(a.input, a.out, *eff); done(a.out, {"effects": " ".join(str(e) for e in eff)})


def cmd_wave(a):
    import numpy as np
    from PIL import Image, ImageDraw
    from common import load_font
    info = probe(a.input)
    rate = 8000 if info["seconds"] > 20 else 22050
    raw = subprocess.run([shutil.which("sox"), "-V1", a.input, "-t", "raw", "-e", "floating-point", "-b", "32",
                          "-c", "1", "-r", str(rate), "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    if not len(x): die("no samples")
    W, H, pad, axis = a.width, a.height, 10, 22
    im = Image.new("RGB", (W, H), (20, 22, 28)); d = ImageDraw.Draw(im)
    mid, amp = (H - axis) // 2, (H - axis) // 2 - pad
    for db in (-6, -12):
        yv = amp * 10 ** (db / 20)
        for yy in (mid - yv, mid + yv): d.line([(0, yy), (W, yy)], fill=(45, 48, 58))
    d.line([(0, mid), (W, mid)], fill=(70, 74, 86))
    cols = np.array_split(x, W)
    for i, c in enumerate(cols):
        if not len(c): continue
        lo, hi = float(c.min()), float(c.max()); r = float(np.sqrt((c * c).mean()))
        d.line([(i, mid - hi * amp), (i, mid - lo * amp)], fill=(90, 170, 255))
        d.line([(i, mid - r * amp), (i, mid + r * amp)], fill=(170, 215, 255))
        if max(abs(lo), abs(hi)) >= 0.999: d.point([(i, pad), (i, H - axis - pad)], fill=(255, 60, 60))
    dur = len(x) / rate; f = load_font(size=12)
    step = next(s for s in (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300) if dur / s <= 12)
    t = 0.0
    while t <= dur + 1e-9:
        px = int(t / dur * (W - 1)); d.line([(px, H - axis), (px, H - axis + 5)], fill=(160, 160, 170))
        d.text((min(px + 2, W - 40), H - axis + 5), f"{t:g}s", font=f, fill=(160, 160, 170)); t += step
    d.text((6, 4), f"{os.path.basename(a.input)}  {dur:.2f}s  peak {info['peak_db']} dBFS", font=f, fill=(200, 200, 210))
    outdir(a.out); im.save(a.out)
    emit({"out": os.path.abspath(a.out), "size": [W, H], "audio": info})


def cmd_spec(a):
    outdir(a.out)
    args = [a.input, "-n", "remix", "-", "spectrogram", "-x", a.width, "-y", a.height, "-o", a.out]
    if a.title: args += ["-t", a.title]
    else: args += ["-t", os.path.basename(a.input)]
    sox(*args, what="SoX spectrogram")
    from PIL import Image
    emit({"out": os.path.abspath(a.out), "size": list(Image.open(a.out).size), "audio": probe(a.input)})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        k = argv.index("--"); extra = argv[k + 1:]; argv = argv[:k]
    ap = argparse.ArgumentParser(prog="bct audio", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def mk(name, inp=True, out_flag=True, multi=False):
        p = sub.add_parser(name)
        if multi: p.add_argument("inputs", nargs="+")
        elif inp: p.add_argument("input")
        if out_flag: p.add_argument("-o", "--out", required=True)
        return p
    t = sub.add_parser("tone"); t.add_argument("out"); t.add_argument("--freq", type=float, default=440)
    t.add_argument("--to", type=float); t.add_argument("--dur", type=float, default=1.0)
    t.add_argument("--wave", default="sine", choices=["sine", "square", "triangle", "sawtooth", "pluck", "trapezium"])
    t.add_argument("--vol", type=float, default=0.5); t.add_argument("--rate", type=int, default=44100)
    n = sub.add_parser("noise"); n.add_argument("out"); n.add_argument("--color", default="white", choices=["white", "pink", "brown"])
    n.add_argument("--dur", type=float, default=1.0); n.add_argument("--vol", type=float, default=0.3); n.add_argument("--rate", type=int, default=44100)
    s = sub.add_parser("synth"); s.add_argument("out"); s.add_argument("--notes", required=True)
    s.add_argument("--bpm", type=float, default=120); s.add_argument("--wave", default="pluck",
                   choices=["sine", "square", "triangle", "sawtooth", "pluck", "trapezium"])
    s.add_argument("--vol", type=float, default=0.7); s.add_argument("--reverb", type=float, default=0); s.add_argument("--rate", type=int, default=44100)
    tr = mk("trim"); tr.add_argument("--start", type=float, default=0); tr.add_argument("--end", type=float); tr.add_argument("--dur", type=float)
    fd = mk("fade"); fd.add_argument("--in", dest="fade_in", type=float, default=0.05); fd.add_argument("--out-time", "--fade-out", dest="fade_out", type=float, default=0.3)
    nm = mk("norm"); nm.add_argument("--db", type=float, default=-1)
    cc = mk("concat", multi=True); cc.add_argument("--gap", type=float, default=0)
    mx = mk("mix", multi=True); mx.add_argument("--vol")
    fx = mk("fx")
    for k in ("reverb", "echo", "pitch", "tempo", "speed", "lowpass", "highpass", "bass", "treble", "gain"):
        fx.add_argument("--" + k, type=float)
    w = mk("wave"); w.add_argument("--width", type=int, default=1200); w.add_argument("--height", type=int, default=300)
    sp = mk("spectrogram"); sp.add_argument("--width", type=int, default=1200); sp.add_argument("--height", type=int, default=400); sp.add_argument("--title")
    mk("probe", out_flag=False)
    a = ap.parse_args(argv); a.extra = extra
    for f in ([a.input] if hasattr(a, "input") else []) + (a.inputs if hasattr(a, "inputs") else []):
        if not os.path.isfile(f): die(f"not found: {f}")
    if a.cmd == "probe": emit(probe(a.input)); return
    {"tone": cmd_tone, "noise": cmd_noise, "synth": cmd_synth, "trim": cmd_trim, "fade": cmd_fade, "norm": cmd_norm,
     "concat": cmd_concat, "mix": cmd_mix, "fx": cmd_fx, "wave": cmd_wave, "spectrogram": cmd_spec}[a.cmd](a)


if __name__ == "__main__":
    main()
