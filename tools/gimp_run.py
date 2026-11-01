"""bct gimp: run GIMP with no window, from the shell.

  bct gimp convert IN OUT [--keep-layers]   open anything GIMP reads (.ora .psd .xcf .png .jpg ...) and save as OUT.
                                            .png/.jpg are flattened; .psd/.xcf/.ora keep layers.
  bct gimp eval "python code"               run GIMP 3 Python (Gimp, Gio, GLib already imported)
  bct gimp script FILE.py                   same, from a file
  [--timeout 180]

Use absolute paths inside your own code (the portable GIMP changes directory when it starts).
Example (GIMP 3):  img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path('/abs/in.png'))
"""
import argparse, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import die, emit

PRE = "from gi.repository import Gimp, Gio, GLib\n"


def find_gimp():
    for g in ("gimp-console", "gimp-console-3.0", "gimp-console-3", "gimp"):
        p = shutil.which(g)
        if p:
            return p
    return None


def run(code, timeout):
    g = find_gimp()
    if not g:
        die("GIMP not found. Run setup.sh (or install gimp).")
    cmd = [g, "-i", "-n", "--quit", "--batch-interpreter=python-fu-eval", "-b", PRE + code]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f"GIMP timed out after {timeout}s")
    log = [l for l in (p.stdout + p.stderr).splitlines() if l.strip() and "dbind-WARNING" not in l and "Broken pipe" not in l]
    err = any("error" in l.lower() or "Traceback" in l for l in log)
    return p.returncode, log, err


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    ap = argparse.ArgumentParser(prog=f"bct gimp {cmd}")
    ap.add_argument("--timeout", type=int, default=180)
    if cmd == "convert":
        ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("--keep-layers", action="store_true")
        a = ap.parse_args(rest)
        src, dst = os.path.abspath(a.src), os.path.abspath(a.dst)
        if not os.path.isfile(src):
            die(f"not found: {a.src}")
        layered = os.path.splitext(dst)[1].lower() in (".psd", ".xcf", ".ora") or a.keep_layers
        if os.path.exists(dst):
            os.remove(dst)
        code = (f"img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path({src!r}))\n"
                + ("" if layered else "img.flatten()\n")
                + f"Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path({dst!r}), None)\n")
        rc, log, err = run(code, a.timeout)
        ok = os.path.isfile(dst) and os.path.getsize(dst) > 0
        emit({"ok": ok, "out": dst if ok else None, "layers_kept": layered, "log": log[-8:] if not ok else []})
        sys.exit(0 if ok else 1)
    if cmd in ("eval", "script"):
        ap.add_argument("code")
        a = ap.parse_args(rest)
        code = open(a.code).read() if cmd == "script" else a.code
        rc, log, err = run(code, a.timeout)
        emit({"exit_code": rc, "error": err, "log": log[-30:]})
        sys.exit(1 if (rc or err) else 0)
    die(f"unknown command '{cmd}' (try: bct gimp --help)")


if __name__ == "__main__":
    main()
