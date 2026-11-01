#!/usr/bin/env bash
# One-shot installer for bot-creative-toolkit on a headless Linux box (x86_64).
# Safe to run again: anything already installed is skipped.
#
#   ./setup.sh             install what's missing
#   ./setup.sh --check     only report what's installed
#   ./setup.sh --no-gimp   skip GIMP (it's the biggest download)
#   ./setup.sh --portable  skip apt and use the official portable builds
#
# Order for each program: already on PATH / known folder -> apt (with sudo) -> official portable build.
# Portable builds go to ~/.local/opt/bct and are linked into ~/.local/bin.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPT="${BCT_OPT:-$HOME/.local/opt/bct}"
BIN="$HOME/.local/bin"
BLENDER_URL="${BCT_BLENDER_URL:-https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz}"
INKSCAPE_URL="${BCT_INKSCAPE_URL:-https://inkscape.org/gallery/item/56343/Inkscape-ebf0e94-x86_64.AppImage}"
GIMP_URL="${BCT_GIMP_URL:-https://download.gimp.org/gimp/v3.0/linux/GIMP-3.0.6-x86_64.AppImage}"
POTRACE_URL="${BCT_POTRACE_URL:-https://potrace.sourceforge.net/download/1.16/potrace-1.16.linux-x86_64.tar.gz}"

CHECK=0; NOGIMP=0; PORTABLE=0
for a in "$@"; do case "$a" in
  --check) CHECK=1;; --no-gimp) NOGIMP=1;; --portable) PORTABLE=1;;
  -h|--help) sed -n 2,11p "$0"; exit 0;;
  *) echo "unknown option: $a"; exit 2;; esac; done

mkdir -p "$BIN" "$OPT"
export PATH="$BIN:$PATH"
FAILED=()
say()  { printf '[setup] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" = 0 ]; then SUDO=" "; elif have sudo && sudo -n true 2>/dev/null; then SUDO="sudo"; fi
APT_UPDATED=0
apt_install() {   # apt_install pkg... ; returns 0 only if every package ends up installed
  [ "$PORTABLE" = 1 ] && return 1
  have apt-get || return 1
  if [ -z "$SUDO" ]; then say "no root/sudo, so apt is not available"; return 1; fi
  if [ "$APT_UPDATED" = 0 ]; then
    say "apt-get update"; $SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -qq >/tmp/bct-apt.log 2>&1 || true
    APT_UPDATED=1
  fi
  say "apt-get install $*"
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "$@" >>/tmp/bct-apt.log 2>&1 \
    || { say "apt could not install $* (log: /tmp/bct-apt.log)"; return 1; }
}
fetch() {  # fetch URL FILE
  say "downloading $1"
  curl -fsSL --retry 4 --retry-all-errors --retry-delay 3 --connect-timeout 20 -o "$2.part" "$1" && mv "$2.part" "$2"
}
appimage_install() {  # appimage_install NAME URL ; extracts to $OPT/NAME (no FUSE needed)
  local name="$1" url="$2" img="$OPT/$1.AppImage"
  [ -f "$img" ] || fetch "$url" "$img" || return 1
  chmod +x "$img"
  rm -rf "$OPT/$name" "$OPT/squashfs-root"
  (cd "$OPT" && "./$name.AppImage" --appimage-extract >/dev/null) || return 1
  mv "$OPT/squashfs-root" "$OPT/$name" && rm -f "$img"
}

# ---------- Python packages (Pillow, numpy) ----------
py_ok() { python3 -c "import PIL, numpy" 2>/dev/null; }
if py_ok; then say "python: Pillow + numpy present"
elif [ "$CHECK" = 1 ]; then say "python: Pillow/numpy MISSING"; FAILED+=(python)
else
  apt_install python3-pil python3-numpy || true
  if ! py_ok; then
    say "pip install --user Pillow numpy"
    python3 -m pip install --user -q Pillow numpy 2>/dev/null \
      || python3 -m pip install --user -q --break-system-packages Pillow numpy || true
  fi
  py_ok && say "python: ok" || { say "python: could not install Pillow/numpy"; FAILED+=(python); }
fi

# ---------- Blender ----------
find_blender() {
  if [ -n "${BLENDER:-}" ] && [ -x "$BLENDER" ]; then echo "$BLENDER"; return; fi
  if have blender; then command -v blender; return; fi
  for b in "$HOME/blender/blender" "$HOME"/blender/*/blender /opt/blender*/blender; do
    [ -x "$b" ] && { echo "$b"; return; }; done
}
B="$(find_blender)"
if [ -n "$B" ]; then say "blender: found $B"
elif [ "$CHECK" = 1 ]; then say "blender: MISSING"; FAILED+=(blender)
else
  mkdir -p "$HOME/blender"
  tarball="$HOME/blender/$(basename "$BLENDER_URL")"
  if fetch "$BLENDER_URL" "$tarball" && tar -xJf "$tarball" -C "$HOME/blender"; then rm -f "$tarball"; fi
  B="$(find_blender)"
  [ -n "$B" ] && say "blender: installed $B" || { say "blender: download failed"; FAILED+=(blender); }
fi
if [ -n "$B" ]; then
  have blender || ln -sf "$B" "$BIN/blender"
  if ! "$B" -b --factory-startup --version >/dev/null 2>&1; then
    say "blender does not start; trying to add its system libraries"
    [ "$CHECK" = 1 ] || apt_install libxi6 libxkbcommon0 libsm6 libgl1 libegl1 libxrender1 libxxf86vm1 libxfixes3 || true
    "$B" -b --factory-startup --version >/dev/null 2>&1 || { say "blender: installed but will not start"; FAILED+=(blender); }
  fi
fi

# ---------- potrace ----------
if have potrace; then say "potrace: found $(command -v potrace)"
elif [ "$CHECK" = 1 ]; then say "potrace: MISSING"; FAILED+=(potrace)
else
  apt_install potrace || {
    t="$OPT/potrace.tar.gz"
    fetch "$POTRACE_URL" "$t" && mkdir -p "$OPT/potrace" && tar -xzf "$t" -C "$OPT/potrace" --strip-components=1 && rm -f "$t" \
      && ln -sf "$OPT/potrace/potrace" "$BIN/potrace"; }
  have potrace && say "potrace: ok" || { say "potrace: install failed"; FAILED+=(potrace); }
fi

# ---------- Inkscape ----------
if have inkscape; then say "inkscape: found $(command -v inkscape)"
elif [ "$CHECK" = 1 ]; then say "inkscape: MISSING"; FAILED+=(inkscape)
else
  apt_install inkscape || {
    appimage_install inkscape "$INKSCAPE_URL" && ln -sf "$OPT/inkscape/AppRun" "$BIN/inkscape"; }
  have inkscape && say "inkscape: ok" || { say "inkscape: install failed"; FAILED+=(inkscape); }
fi

# ---------- GIMP ----------
gimp_cmd() { for g in gimp-console gimp-console-3.0 gimp-console-2.10 gimp; do have "$g" && { command -v "$g"; return; }; done; }
if [ "$NOGIMP" = 1 ]; then say "gimp: skipped (--no-gimp)"
elif [ -n "$(gimp_cmd)" ]; then say "gimp: found $(gimp_cmd)"
elif [ "$CHECK" = 1 ]; then say "gimp: MISSING"; FAILED+=(gimp)
else
  apt_install gimp || {
    if appimage_install gimp "$GIMP_URL"; then
      # the AppImage's AppRun starts the GUI binary; make a copy that starts gimp-console instead
      sed 's#usr/bin/org.gimp.GIMP.Stable#usr/bin/gimp-console-3.0#' "$OPT/gimp/AppRun" > "$OPT/gimp/AppRun-console"
      chmod +x "$OPT/gimp/AppRun-console"
      cat > "$BIN/gimp-console" <<EOS
#!/bin/sh
export APPDIR="$OPT/gimp"
exec "$OPT/gimp/AppRun-console" "\$@"
EOS
      chmod +x "$BIN/gimp-console"
    fi; }
  [ -n "$(gimp_cmd)" ] && say "gimp: ok" || { say "gimp: install failed"; FAILED+=(gimp); }
fi

# ---------- the bct command ----------
chmod +x "$HERE/bin/bct" "$HERE/selftest.sh" 2>/dev/null
[ "$CHECK" = 1 ] || ln -sf "$HERE/bin/bct" "$BIN/bct"
say "bct: $( [ -x "$BIN/bct" ] && echo "$BIN/bct" || echo "not linked")  (add ~/.local/bin to PATH if 'bct' is not found)"

if [ ${#FAILED[@]} -gt 0 ]; then say "NOT READY: ${FAILED[*]}"; exit 1; fi
say "READY. Next: ./selftest.sh"
