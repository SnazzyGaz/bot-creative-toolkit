"""Used by setup.sh: fill in shared libraries a portable .deb build is missing, from the distro's own archive.

  python3 deb_fill.py ROOT BINARY...     (ROOT = the folder a .deb was unpacked into)

Runs ldd on each BINARY with ROOT's lib folders on LD_LIBRARY_PATH, maps each missing soname to the Debian/Ubuntu
package name that normally holds it (libFoo-3_1.so.30 -> libfoo-3-1-30, also tried with the t64 suffix), looks the
package up in the archive index for this release, downloads it over HTTPS and unpacks it into ROOT. Repeats until
nothing is missing or nothing more can be found. Prints what it did; exits 1 if libraries are still missing.
"""
import io, lzma, os, re, subprocess, sys, urllib.request

def osrel():
    d = {}
    for line in open("/etc/os-release"):
        if "=" in line:
            k, v = line.rstrip().split("=", 1); d[k] = v.strip('"')
    return d

def libdirs(root):
    return [os.path.join(root, p) for p in ("usr/lib", "usr/lib/x86_64-linux-gnu", "lib/x86_64-linux-gnu")]

def missing(root, bins):
    env = dict(os.environ, LD_LIBRARY_PATH=":".join(libdirs(root)))
    out = set()
    for b in bins:
        p = subprocess.run(["ldd", b], capture_output=True, text=True, env=env)
        out |= set(re.findall(r"^\s*(\S+) => not found", p.stdout, re.M))
    for d in libdirs(root):   # libraries pulled in earlier can need more
        if os.path.isdir(d):
            for f in os.listdir(d):
                if ".so" in f and os.path.isfile(os.path.join(d, f)):
                    p = subprocess.run(["ldd", os.path.join(d, f)], capture_output=True, text=True, env=env)
                    out |= set(re.findall(r"^\s*(\S+) => not found", p.stdout, re.M))
    return sorted(out)

def candidates(soname):
    m = re.match(r"(lib.+?)\.so\.(\d+)", soname)
    if not m: return []
    base = m.group(1).lower().replace("_", "-").replace(".", "-")
    name = base + ("-" if base[-1].isdigit() else "") + m.group(2)
    return [name, name + "t64"]

def index(rel):
    did, code = rel.get("ID", ""), rel.get("VERSION_CODENAME", "")
    like = rel.get("ID_LIKE", "")
    if did == "ubuntu" or "ubuntu" in like:
        mirror, comps = "https://archive.ubuntu.com/ubuntu", ["main", "universe"]
        code = rel.get("UBUNTU_CODENAME", code)
    elif did == "debian" or "debian" in like:
        mirror, comps = "https://deb.debian.org/debian", ["main"]
    else:
        sys.exit("deb_fill: not a Debian/Ubuntu system")
    pk = {}
    for c in comps:
        url = f"{mirror}/dists/{code}/{c}/binary-amd64/Packages.xz"
        txt = lzma.decompress(urllib.request.urlopen(url, timeout=60).read()).decode("utf-8", "replace")
        for block in txt.split("\n\n"):
            n = re.search(r"^Package: (\S+)", block, re.M); f = re.search(r"^Filename: (\S+)", block, re.M)
            if n and f: pk[n.group(1)] = f"{mirror}/{f.group(1)}"
    return pk

def unpack(url, root):
    data = urllib.request.urlopen(url, timeout=120).read()
    tmp = os.path.join(root, ".fill.deb"); open(tmp, "wb").write(data)
    subprocess.run(["dpkg-deb", "-x", tmp, root], check=True); os.remove(tmp)

def main():
    root, bins = sys.argv[1], sys.argv[2:]
    pk, tried = None, set()
    while True:
        miss = [m for m in missing(root, bins) if m not in tried]
        if not miss: break
        pk = pk or index(osrel())
        for so in miss:
            tried.add(so)
            for c in candidates(so):
                if c in pk:
                    print(f"[deb_fill] {so} <- {c}"); unpack(pk[c], root); break
            else:
                print(f"[deb_fill] no package found for {so}")
    left = missing(root, bins)
    if left: print("[deb_fill] still missing: " + " ".join(left)); sys.exit(1)
    print("[deb_fill] all libraries found")

if __name__ == "__main__":
    main()
