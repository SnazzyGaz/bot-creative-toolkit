"""bct video: frames to MP4/GIF, Blender turntables, trimming, and frame contact sheets, with FFmpeg.

  encode FRAMES -o OUT.mp4|OUT.gif|OUT.webm [--fps 24] [--width W] [--crf 20] [--gif-colors 256] [--dither sierra2_4a]
        FRAMES: a folder of images, a glob ("shots/*.png") or a printf pattern ("f_%04d.png"); sorted by name
  turntable MODEL -o OUT.mp4 [--gif OUT.gif] [--frames 48] [--fps 24] [--size 480] [--samples 16]
        [--engine cycles|workbench|eevee] [--elev 0.35] [--import-scale 0.001] [--clay] [--keep-frames DIR]
        MODEL: anything `bct look` takes (.blend, bpy .py, .stl/.obj/.ply/.glb)
  trim IN -o OUT --start 1.5 (--end 4 | --duration 2.5) [--copy]
        re-encodes by default (frame-exact); --copy is instant but cuts on keyframes
  sheet IN -o sheet.png [--count 9] [--cols 3] [--width 320]
        evenly spaced frames in one labelled image, so you can look at a video in one go
  probe IN
        duration, frame count, fps, size and codec as JSON
"""
import argparse, glob, json, os, shutil, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit, load_font

HERE = os.path.dirname(os.path.abspath(__file__))


def tool(name):
    p = shutil.which(name)
    if not p:
        die(f"{name} not found. Run setup.sh")
    return p


def run(cmd, what):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-12:])
        die(f"{what} failed:\n{tail}", 1)
    return p


def probe(path, count=True):
    """Duration, frames, fps, size, codec of the first video stream."""
    cmd = [tool("ffprobe"), "-v", "error", "-select_streams", "v:0"]
    if count:
        cmd += ["-count_frames"]
    cmd += ["-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_frames,nb_read_frames,pix_fmt:format=duration,size",
            "-of", "json", path]
    d = json.loads(run(cmd, "ffprobe").stdout)
    st = (d.get("streams") or [{}])[0]; fm = d.get("format", {})
    num, _, den = st.get("r_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0
    frames = st.get("nb_read_frames") or st.get("nb_frames")
    return {"path": os.path.abspath(path), "codec": st.get("codec_name"), "width": st.get("width"),
            "height": st.get("height"), "fps": round(fps, 3), "frames": int(frames) if frames else None,
            "duration": round(float(fm.get("duration", 0) or 0), 3), "pix_fmt": st.get("pix_fmt"),
            "bytes": int(fm.get("size", 0) or os.path.getsize(path))}


def frame_input(src, fps):
    """ffmpeg input args for a folder, a glob or a printf pattern."""
    if os.path.isdir(src):
        files = sorted(f for f in glob.glob(os.path.join(src, "*")) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")))
    elif "%" in src:
        return ["-framerate", str(fps), "-i", src], None
    else:
        files = sorted(glob.glob(src))
    if not files:
        die(f"no frames found in {src}")
    # a concat list keeps the exact sorted order and works for any file names
    lst = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    for f in files:
        lst.write(f"file '{os.path.abspath(f)}'\nduration {1 / fps:.6f}\n")
    lst.write(f"file '{os.path.abspath(files[-1])}'\n")   # concat demuxer ignores the last duration otherwise
    lst.close()
    return ["-f", "concat", "-safe", "0", "-i", lst.name], len(files)


def encode_to(inp, out, fps, width=None, crf=20, gif_colors=256, dither="sierra2_4a", nframes=None):
    ext = os.path.splitext(out)[1].lower()
    scale = f"scale={width}:-2:flags=lanczos" if width else "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    ff = [tool("ffmpeg"), "-y", "-v", "error"] + inp
    lim = ["-frames:v", str(nframes)] if nframes else []
    if ext == ".gif":
        sc = f"scale={width}:-1:flags=lanczos" if width else "null"
        vf = (f"fps={fps},{sc},split[a][b];[a]palettegen=max_colors={gif_colors}:stats_mode=diff[p];"
              f"[b][p]paletteuse=dither={dither}:diff_mode=rectangle")
        cmd = ff + ["-vf", vf, "-loop", "0"] + lim + [out]
    elif ext == ".webm":
        cmd = ff + ["-vf", f"fps={fps},{scale}", "-c:v", "libvpx-vp9", "-crf", str(crf + 12), "-b:v", "0",
                    "-pix_fmt", "yuv420p"] + lim + [out]
    else:
        cmd = ff + ["-vf", f"fps={fps},{scale}", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart"] + lim + [out]
    run(cmd, "ffmpeg encode")
    return probe(out)


def cmd_encode(a):
    inp, n = frame_input(a.frames, a.fps)
    t = time.time()
    res = encode_to(inp, a.out, a.fps, a.width, a.crf, a.gif_colors, a.dither, n)
    res.update({"input_frames": n, "seconds": round(time.time() - t, 2)})
    emit(res)


def cmd_turntable(a):
    frames_dir = os.path.abspath(a.keep_frames) if a.keep_frames else tempfile.mkdtemp(prefix="bct_turn_")
    look = [sys.executable, os.path.join(HERE, "look.py"), a.model, "--orbit", str(a.frames), "--frames-dir", frames_dir,
            "--orbit-elev", str(a.elev), "--size", str(a.size), "--samples", str(a.samples), "--engine", a.engine,
            "--import-scale", str(a.import_scale), "--margin", str(a.margin)] + (["--clay"] if a.clay else [])
    t = time.time()
    p = subprocess.run(look, capture_output=True, text=True)
    if p.returncode != 0:
        die("rendering the turntable failed:\n" + p.stderr.strip()[-1500:], 1)
    info = json.loads(p.stdout); render_s = round(time.time() - t, 1)
    inp, n = frame_input(frames_dir, a.fps)
    res = {"render_seconds": render_s, "frames_rendered": n, "size_m": info.get("size_m"),
           "triangles": info.get("triangles"), "mp4": encode_to(inp, a.out, a.fps, None, a.crf, nframes=n)}
    if a.gif:
        inp, n = frame_input(frames_dir, a.fps)
        res["gif"] = encode_to(inp, a.gif, a.fps, a.gif_width, gif_colors=a.gif_colors, dither=a.dither, nframes=n)
    if a.keep_frames:
        res["frames_dir"] = frames_dir
    else:
        shutil.rmtree(frames_dir, ignore_errors=True)
    emit(res)


def cmd_trim(a):
    if a.end is None and a.duration is None:
        die("give --end or --duration")
    dur = a.duration if a.duration is not None else a.end - a.start
    if dur <= 0:
        die("the end must be after the start")
    ff = [tool("ffmpeg"), "-y", "-v", "error", "-ss", str(a.start), "-i", a.input]
    ext = os.path.splitext(a.out)[1].lower()
    fps = probe(a.input, count=False)["fps"]
    if fps and not a.copy:   # -t can drop the last frame to rounding, so ask for the exact frame count
        ff += ["-frames:v", str(max(1, round(dur * fps)))] + ([] if ext == ".gif" else ["-t", str(dur + 1 / fps)])
    else:
        ff += ["-t", str(dur)]
    if a.copy:
        cmd = ff + ["-c", "copy", "-avoid_negative_ts", "make_zero", a.out]
    elif ext == ".gif":
        cmd = ff + ["-vf", "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a", a.out]
    else:
        cmd = ff + ["-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-movflags", "+faststart", a.out]
    run(cmd, "ffmpeg trim")
    emit(probe(a.out))


def cmd_sheet(a):
    from PIL import Image, ImageDraw
    info = probe(a.input, count=False)
    dur = info["duration"] or 0
    n = max(1, a.count)
    times = [dur * (i + 0.5) / n for i in range(n)]
    tmp = tempfile.mkdtemp(prefix="bct_sheet_")
    tiles = []
    for i, t in enumerate(times):
        f = os.path.join(tmp, f"{i:03d}.png")
        run([tool("ffmpeg"), "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", a.input, "-frames:v", "1",
             "-vf", f"scale={a.width}:-1", f], "ffmpeg frame grab")
        if os.path.isfile(f):
            tiles.append((t, Image.open(f).convert("RGB")))
    if not tiles:
        die("could not read any frames", 1)
    w, h = tiles[0][1].size
    cols = a.cols or min(len(tiles), 3)
    rows = (len(tiles) + cols - 1) // cols
    lab = max(16, w // 16)
    head = lab + 6
    sheet = Image.new("RGB", (cols * w, head + rows * (h + lab)), (24, 24, 24))
    d = ImageDraw.Draw(sheet); f = load_font(None, int(lab * 0.75))
    d.text((6, 3), f"{os.path.basename(a.input)} | {info['width']}x{info['height']} {info['fps']:g} fps {dur:.2f} s",
           fill=(235, 235, 235), font=f)
    for i, (t, im) in enumerate(tiles):
        x, y = (i % cols) * w, head + (i // cols) * (h + lab)
        d.text((x + 6, y + 1), f"{t:.2f} s", fill=(255, 210, 90), font=f)
        sheet.paste(im, (x, y + lab))
    sheet.save(a.out)
    shutil.rmtree(tmp, ignore_errors=True)
    emit({"sheet": os.path.abspath(a.out), "times": [round(t, 3) for t, _ in tiles], "video": info})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bct video", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("encode"); e.add_argument("frames"); e.add_argument("-o", "--out", required=True)
    e.add_argument("--fps", type=float, default=24); e.add_argument("--width", type=int)
    e.add_argument("--crf", type=int, default=20); e.add_argument("--gif-colors", type=int, default=256)
    e.add_argument("--dither", default="sierra2_4a", help="GIF dither: sierra2_4a, bayer, floyd_steinberg, none")
    t = sub.add_parser("turntable"); t.add_argument("model"); t.add_argument("-o", "--out", required=True)
    t.add_argument("--gif"); t.add_argument("--gif-width", type=int, default=None)
    t.add_argument("--frames", type=int, default=48); t.add_argument("--fps", type=float, default=24)
    t.add_argument("--size", type=int, default=480); t.add_argument("--samples", type=int, default=16)
    t.add_argument("--engine", default="cycles", choices=["cycles", "eevee", "workbench"])
    t.add_argument("--elev", type=float, default=0.35); t.add_argument("--margin", type=float, default=1.0)
    t.add_argument("--import-scale", type=float, default=1.0); t.add_argument("--clay", action="store_true")
    t.add_argument("--crf", type=int, default=20); t.add_argument("--gif-colors", type=int, default=128)
    t.add_argument("--dither", default="sierra2_4a"); t.add_argument("--keep-frames")
    r = sub.add_parser("trim"); r.add_argument("input"); r.add_argument("-o", "--out", required=True)
    r.add_argument("--start", type=float, default=0); r.add_argument("--end", type=float)
    r.add_argument("--duration", type=float); r.add_argument("--copy", action="store_true")
    r.add_argument("--crf", type=int, default=20)
    s = sub.add_parser("sheet"); s.add_argument("input"); s.add_argument("-o", "--out", required=True)
    s.add_argument("--count", type=int, default=9); s.add_argument("--cols", type=int)
    s.add_argument("--width", type=int, default=320)
    p = sub.add_parser("probe"); p.add_argument("input")
    a = ap.parse_args(argv)
    if a.cmd in ("trim", "sheet", "probe") and not os.path.isfile(a.input):
        die(f"not found: {a.input}")
    {"encode": cmd_encode, "turntable": cmd_turntable, "trim": cmd_trim, "sheet": cmd_sheet,
     "probe": lambda a: emit(probe(a.input))}[a.cmd](a)


if __name__ == "__main__":
    main()
