#!/usr/bin/env bash
# One-shot installer for bot-creative-toolkit on a headless Linux box (x86_64).
# Safe to run again: anything already installed is skipped.
#
#   ./setup.sh             install what's missing
#   ./setup.sh --check     only report what's installed
#   ./setup.sh --no-gimp   skip GIMP (it's the biggest download)
#   ./setup.sh --no-extra  skip FFmpeg, ImageMagick and OpenSCAD
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
FFMPEG_URL="${BCT_FFMPEG_URL:-https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz}"
MAGICK_URL="${BCT_MAGICK_URL:-}"        # empty: newest gcc x86_64 AppImage from GitHub releases, then a pinned one
MAGICK_PINNED="https://github.com/ImageMagick/ImageMagick/releases/download/7.1.2-35/ImageMagick-7.1.2-35-gcc-x86_64.AppImage"
OPENSCAD_URL="${BCT_OPENSCAD_URL:-}"    # empty: newest nightly AppImage (has the fast Manifold backend), then 2021.01
OPENSCAD_STABLE="https://files.openscad.org/OpenSCAD-2021.01-x86_64.AppImage"

CHECK=0; NOGIMP=0; PORTABLE=0; NOEXTRA=0
for a in "$@"; do case "$a" in
  --check) CHECK=1;; --no-gimp) NOGIMP=1;; --no-extra) NOEXTRA=1;; --portable) PORTABLE=1;;
  -h|--help) sed -n 2,12p "$0"; exit 0;;
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

# ---------- FFmpeg (video) ----------
if [ "$NOEXTRA" = 1 ]; then say "ffmpeg/imagemagick/openscad: skipped (--no-extra)"
else
if have ffmpeg && have ffprobe; then say "ffmpeg: found $(command -v ffmpeg)"
elif [ "$CHECK" = 1 ]; then say "ffmpeg: MISSING"; FAILED+=(ffmpeg)
else
  apt_install ffmpeg || {
    t="$OPT/ffmpeg.tar.xz"
    fetch "$FFMPEG_URL" "$t" && rm -rf "$OPT/ffmpeg" && mkdir -p "$OPT/ffmpeg" \
      && tar -xJf "$t" -C "$OPT/ffmpeg" --strip-components=1 && rm -f "$t" \
      && ln -sf "$OPT/ffmpeg/ffmpeg" "$BIN/ffmpeg" && ln -sf "$OPT/ffmpeg/ffprobe" "$BIN/ffprobe"; }
  have ffmpeg && have ffprobe && say "ffmpeg: ok" || { say "ffmpeg: install failed"; FAILED+=(ffmpeg); }
fi

# ---------- ImageMagick 7 (the `magick` command) ----------
if have magick; then say "imagemagick: found $(command -v magick)"
elif [ "$CHECK" = 1 ]; then say "imagemagick: MISSING (need ImageMagick 7 'magick')"; FAILED+=(imagemagick)
else
  apt_install imagemagick || true      # older distros ship ImageMagick 6 (no `magick`), then the AppImage is used
  if ! have magick; then
    url="$MAGICK_URL"
    [ -n "$url" ] || url="$(curl -fsSL --retry 3 https://api.github.com/repos/ImageMagick/ImageMagick/releases/latest 2>/dev/null \
      | grep -oE 'https://[^"]+gcc-x86_64\.AppImage' | head -1)"
    appimage_install imagemagick "${url:-$MAGICK_PINNED}" || appimage_install imagemagick "$MAGICK_PINNED"
    [ -x "$OPT/imagemagick/AppRun" ] && ln -sf "$OPT/imagemagick/AppRun" "$BIN/magick"
  fi
  have magick && say "imagemagick: ok" || { say "imagemagick: install failed"; FAILED+=(imagemagick); }
fi

# ---------- OpenSCAD ----------
if have openscad; then say "openscad: found $(command -v openscad)"
elif [ "$CHECK" = 1 ]; then say "openscad: MISSING"; FAILED+=(openscad)
else
  url="$OPENSCAD_URL"
  if [ -z "$url" ]; then
    n="$(curl -fsSL --retry 3 https://files.openscad.org/snapshots/ 2>/dev/null \
      | grep -oE 'OpenSCAD-[0-9.]+-x86_64\.AppImage' | sort -uV | tail -1)"
    [ -n "$n" ] && url="https://files.openscad.org/snapshots/$n"
  fi
  # the nightly is preferred over apt: apt's 2021.01 has no Manifold backend and is far slower
  { [ -n "$url" ] && appimage_install openscad "$url"; } || appimage_install openscad "$OPENSCAD_STABLE" || apt_install openscad || true
  [ -x "$OPT/openscad/AppRun" ] && ln -sf "$OPT/openscad/AppRun" "$BIN/openscad"
  have openscad && say "openscad: ok" || { say "openscad: install failed"; FAILED+=(openscad); }
fi
fi

# ---------- the bct command ----------
chmod +x "$HERE/bin/bct" "$HERE/selftest.sh" 2>/dev/null
[ "$CHECK" = 1 ] || ln -sf "$HERE/bin/bct" "$BIN/bct"
say "bct: $( [ -x "$BIN/bct" ] && echo "$BIN/bct" || echo "not linked")  (add ~/.local/bin to PATH if 'bct' is not found)"

if [ ${#FAILED[@]} -gt 0 ]; then say "NOT READY: ${FAILED[*]}"; exit 1; fi
say "READY. Next: ./selftest.sh"
