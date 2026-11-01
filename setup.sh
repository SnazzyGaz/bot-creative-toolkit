#!/usr/bin/env bash
# One-shot installer for bot-creative-toolkit on a headless Linux box (x86_64).
# Safe to run again: anything already installed is skipped.
#
#   ./setup.sh             install what's missing
#   ./setup.sh --check     only report what's installed
#   ./setup.sh --no-gimp   skip GIMP (it's the biggest download)
#   ./setup.sh --no-extra  skip FFmpeg, ImageMagick and OpenSCAD
#   ./setup.sh --no-art    skip Krita, G'MIC, FontForge and SoX
#   ./setup.sh --no-krita  skip only Krita (390 MB download, 1.1 GB unpacked)
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

KRITA_URL="${BCT_KRITA_URL:-}"          # empty: newest stable AppImage on download.kde.org, then a pinned one
KRITA_PINNED="https://download.kde.org/stable/krita/6.0.4.1/krita-6.0.4.1-x86_64.AppImage"
FONTFORGE_URL="${BCT_FONTFORGE_URL:-}"  # empty: newest AppImage from GitHub releases, then a pinned one
FONTFORGE_PINNED="https://github.com/fontforge/fontforge/releases/download/20251009/FontForge-2025-10-09-Linux-x86_64.AppImage"
MICROMAMBA_URL="${BCT_MICROMAMBA_URL:-https://micro.mamba.pm/api/micromamba/linux-64/latest}"

CHECK=0; NOGIMP=0; PORTABLE=0; NOEXTRA=0; NOART=0; NOKRITA=0
for a in "$@"; do case "$a" in
  --check) CHECK=1;; --no-gimp) NOGIMP=1;; --no-extra) NOEXTRA=1;; --no-art) NOART=1;; --no-krita) NOKRITA=1;; --portable) PORTABLE=1;;
  -h|--help) sed -n 2,14p "$0"; exit 0;;
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

# ---------- Krita, G'MIC, FontForge, SoX ----------
if [ "$NOART" = 1 ]; then say "krita/gmic/fontforge/sox: skipped (--no-art)"
else
# Krita (and Xvfb, because Krita needs an X display even for --export)
if [ "$NOKRITA" = 1 ]; then say "krita: skipped (--no-krita)"
else
if have krita; then say "krita: found $(command -v krita)"
elif [ "$CHECK" = 1 ]; then say "krita: MISSING"; FAILED+=(krita)
else
  url="$KRITA_URL"
  if [ -z "$url" ]; then   # newest version folder that has an x86_64 AppImage
    for v in $(curl -fsSL --retry 3 https://download.kde.org/stable/krita/ 2>/dev/null | grep -oE 'href="[0-9][0-9.]*/"' \
               | grep -oE '[0-9][0-9.]*[0-9]' | sort -uV | tail -4 | sort -rV); do
      n="$(curl -fsSL "https://download.kde.org/stable/krita/$v/" 2>/dev/null | grep -oE 'krita-[0-9.]+-x86_64\.AppImage' | head -1)"
      [ -n "$n" ] && { url="https://download.kde.org/stable/krita/$v/$n"; break; }
    done
  fi
  # the AppImage is preferred: it is current and brings kritarunner + its own Python for scripts
  { [ -n "$url" ] && appimage_install krita "$url"; } || appimage_install krita "$KRITA_PINNED" || apt_install krita || true
  if [ -x "$OPT/krita/AppRun" ]; then
    ln -sf "$OPT/krita/AppRun" "$BIN/krita"
    py="$(ls -d "$OPT"/krita/usr/lib/python3.* 2>/dev/null | head -1)"
    cat > "$BIN/kritarunner" <<KR
#!/usr/bin/env bash
# kritarunner from the Krita AppImage: runs one Python script inside Krita and exits
export LD_LIBRARY_PATH="$OPT/krita/usr/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export PYTHONHOME="$OPT/krita/usr"
exec "$OPT/krita/usr/bin/kritarunner" "\$@"
KR
    chmod +x "$BIN/kritarunner"
  fi
  have krita && say "krita: ok" || { say "krita: install failed"; FAILED+=(krita); }
fi
if have xvfb-run || [ -n "${DISPLAY:-}" ]; then say "xvfb: $(command -v xvfb-run || echo "using DISPLAY=$DISPLAY")"
elif [ "$CHECK" = 1 ]; then say "xvfb: MISSING (Krita needs xvfb-run or a DISPLAY)"; FAILED+=(xvfb)
else apt_install xvfb xauth || true
  have xvfb-run && say "xvfb: ok" || { say "xvfb: could not install; Krita commands will need a DISPLAY"; FAILED+=(xvfb); }
fi
fi

# G'MIC (command-line filters)
GMIC_VER=""
if have gmic; then say "gmic: found $(command -v gmic)"
elif [ "$CHECK" = 1 ]; then say "gmic: MISSING"; FAILED+=(gmic)
else
  apt_install gmic || true
  if ! have gmic && [ -r /etc/os-release ] && have dpkg-deb; then
    # official .deb from gmic.eu for this Debian/Ubuntu release, unpacked (no root needed); missing libs from the archive
    . /etc/os-release
    page="$(curl -fsSL --retry 3 https://gmic.eu/download.html 2>/dev/null)"
    code="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    deb="$(printf '%s' "$page" | grep -oE "linux/gmic_[0-9.]+_[a-z0-9-]+_${code}_amd64\.deb" | head -1)"
    if [ -n "$code" ] && [ -n "$deb" ]; then
      rm -rf "$OPT/gmic" && mkdir -p "$OPT/gmic/root"
      fetch "https://gmic.eu/get_file.php?file=$deb" "$OPT/gmic/gmic.deb" \
        && dpkg-deb -x "$OPT/gmic/gmic.deb" "$OPT/gmic/root" && rm -f "$OPT/gmic/gmic.deb" \
        && python3 "$HERE/tools/deb_fill.py" "$OPT/gmic/root" "$OPT/gmic/root/usr/bin/gmic"
      cat > "$BIN/gmic" <<GM
#!/usr/bin/env bash
export LD_LIBRARY_PATH="$OPT/gmic/root/usr/lib:$OPT/gmic/root/usr/lib/x86_64-linux-gnu\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
exec "$OPT/gmic/root/usr/bin/gmic" "\$@"
GM
      chmod +x "$BIN/gmic"
    else say "gmic: no gmic.eu build for this system; install G'MIC with your package manager"; fi
  fi
  gmic -v -1 version >/dev/null 2>&1 && say "gmic: ok" || { say "gmic: install failed"; FAILED+=(gmic); }
fi
# the G'MIC filter library source, so `bct fx` can list every filter and use the GUI default settings
if have gmic; then
  GMIC_VER="$(gmic -v -1 version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  LIB="$OPT/gmic-stdlib/gmic_stdlib_${GMIC_VER}.gmic"
  if [ -s "$LIB" ]; then say "gmic filter list: $LIB"
  elif [ "$CHECK" = 1 ]; then say "gmic filter list: missing (bct fx gui/list --all need it; re-run setup.sh)"
  else mkdir -p "$OPT/gmic-stdlib"
    fetch "https://raw.githubusercontent.com/GreycLab/gmic/v.${GMIC_VER}/src/gmic_stdlib.gmic" "$LIB" \
      && say "gmic filter list: ok" || say "gmic filter list: download failed (bct fx still works with its own styles)"
  fi
fi

# FontForge (with its Python module)
ff_ok() { have fontforge && fontforge -lang=py -c "import fontforge" >/dev/null 2>&1; }
if ff_ok; then say "fontforge: found $(command -v fontforge)"
elif [ "$CHECK" = 1 ]; then say "fontforge: MISSING"; FAILED+=(fontforge)
else
  apt_install fontforge python3-fontforge || true
  if ! ff_ok; then
    url="$FONTFORGE_URL"
    [ -n "$url" ] || url="$(curl -fsSL --retry 3 https://api.github.com/repos/fontforge/fontforge/releases/latest 2>/dev/null \
      | grep -oE 'https://[^"]+x86_64\.AppImage' | head -1)"
    appimage_install fontforge "${url:-$FONTFORGE_PINNED}" || appimage_install fontforge "$FONTFORGE_PINNED"
    # a wrapper, not a symlink: this AppRun finds its files relative to $0. It also changes the working folder,
    # so always give fontforge absolute paths.
    [ -x "$OPT/fontforge/AppRun" ] && rm -f "$BIN/fontforge" \
      && printf '#!/usr/bin/env bash\nexec "%s" "$@"\n' "$OPT/fontforge/AppRun" > "$BIN/fontforge" && chmod +x "$BIN/fontforge"
  fi
  ff_ok && say "fontforge: ok" || { say "fontforge: install failed"; FAILED+=(fontforge); }
fi

# SoX (audio)
if have sox && have soxi; then say "sox: found $(command -v sox)"
elif [ "$CHECK" = 1 ]; then say "sox: MISSING"; FAILED+=(sox)
else
  apt_install sox libsox-fmt-all || true
  if ! have sox; then
    # there is no official static SoX; conda-forge's build (via the single-file micromamba) works on any x86_64 Linux
    mm="$OPT/micromamba/bin/micromamba"
    [ -x "$mm" ] || { fetch "$MICROMAMBA_URL" "$OPT/micromamba.tar.bz2" \
      && mkdir -p "$OPT/micromamba" && python3 -c "import tarfile,sys; tarfile.open(sys.argv[1]).extract('bin/micromamba', sys.argv[2], filter='data')" \
         "$OPT/micromamba.tar.bz2" "$OPT/micromamba" && rm -f "$OPT/micromamba.tar.bz2"; }
    [ -x "$mm" ] && rm -rf "$OPT/sox" && MAMBA_ROOT_PREFIX="$OPT/micromamba/root" "$mm" create -y -q -p "$OPT/sox" -c conda-forge sox \
      >/tmp/bct-sox.log 2>&1 && ln -sf "$OPT/sox/bin/sox" "$BIN/sox" && ln -sf "$OPT/sox/bin/soxi" "$BIN/soxi"
  fi
  have sox && have soxi && say "sox: ok" || { say "sox: install failed (log: /tmp/bct-sox.log)"; FAILED+=(sox); }
fi
fi

# ---------- the bct command ----------
chmod +x "$HERE/bin/bct" "$HERE/selftest.sh" 2>/dev/null
[ "$CHECK" = 1 ] || ln -sf "$HERE/bin/bct" "$BIN/bct"
say "bct: $( [ -x "$BIN/bct" ] && echo "$BIN/bct" || echo "not linked")  (add ~/.local/bin to PATH if 'bct' is not found)"

if [ ${#FAILED[@]} -gt 0 ]; then say "NOT READY: ${FAILED[*]}"; exit 1; fi
say "READY. Next: ./selftest.sh"
