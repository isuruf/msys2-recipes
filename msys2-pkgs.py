from bs4 import BeautifulSoup
import requests
import subprocess
import os
import shutil

index_url = 'https://repo.msys2.org/msys/x86_64/'

to_process = set(["git", "automake-wrapper", "make", "sed", "libtool", "autoconf",
    "findutils", "m4", "bash", "texinfo", "p7zip", "curl", "base", "tar", "zip",
    "unzip", "diffutils", "patch", "patchutils"])

provides = {"sh": "bash", "libuuid": "libutil-linux", "awk": "gawk",
        "perl-IO-stringy": "perl-IO-Stringy"}

seen = {}

def get_pkgs():
    directory_listing = requests.get(index_url).text
    s = BeautifulSoup(directory_listing, 'html.parser')
    full_names = [node.get('href') for node in s.find_all('a') if node.get('href').endswith((".tar.zst", "tar.xz"))]
    # format: msy2-w32api-headers-10.0.0.r16.g49a56d453-1-x86_64.pkg.tar.zst
    return list(sorted([("-".join(pkg.split('-')[:-3]), "-".join(pkg.split('-')[-3:])) for pkg in full_names]))

pkg_latest_ver = dict(get_pkgs())
# for pkg, info in pkg_latest_ver.items():
#    print(pkg, info)

def get_info(pkginfo, desc):
    return [line[len(f"{desc} = "):].strip() for line in pkginfo if line.startswith(f"{desc} = ")]

def get_depends(pkg):
    info = pkg_latest_ver[pkg]
    basename = f"cache/{pkg}-{info}"
    url = f"{index_url}/{pkg}-{info}"
    if not os.path.exists(basename):
        subprocess.check_call(["wget", url, "-O", basename])
    subprocess.check_call(["mkdir", "-p", "cache/tmp"])
    subprocess.check_call(["tar", "-xf", basename, "--directory=cache/tmp"])
    with open("cache/tmp/.PKGINFO") as f:
        pkginfo = f.readlines()
    depends = get_info(pkginfo, "depend")
    depends = [dep for dep in depends if not dep.startswith("pacman")]
    license_text = get_info(pkginfo, "license")[0]
    spdx = license_text[5:] if license_text.startswith("spdx:") else license_text
    desc = get_info(pkginfo, "pkgdesc")[0]
    url = get_info(pkginfo, "url")[0]
    return depends, spdx, desc, url

while to_process:
    pkg = to_process.pop()
    depends, spdx, desc, url = get_depends(pkg)
    for i, full_dep in enumerate(depends):
        dep = full_dep.split(">")[0].split("=")[0].split("<")[0]
        cond = full_dep[len(dep):]
        dep = provides.get(dep, dep)
        if cond:
            depends[i] = f"{dep} {cond}"
        if dep not in seen:
            to_process.add(dep)
    seen[pkg] = depends, spdx, desc, url

with open("template/meta.yaml") as f:
    template = f.read()

for pkg, (depends, spdx, desc, url) in seen.items():
    print(f"{pkg} {pkg_latest_ver[pkg]} {' '.join(depends)}")
    subprocess.check_call(["mkdir", "-p", f"recipes/m2-{pkg}"])
    info = pkg_latest_ver[pkg]
    sha256 = subprocess.check_output(["sha256sum", f"cache/{pkg}-{info}"]).decode("utf-8").split(" ")[0]
    meta = template
    info = {
        "name": pkg,
        "version": ".".join(info.split("-")[:2] ),
        "tarname": f"{pkg}-{info}",
        "depends": "\n".join(f"    - m2-{dep}" for dep in depends),
        "license": spdx,
        "summary": desc,
        "url": url,
        "sha256": sha256,
    }
    for k, v in info.items():
        meta = meta.replace(f"{{{{ {k} }}}}", v)
    with open(f"recipes/m2-{pkg}/meta.yaml", "w") as f:
        f.write(meta)
    shutil.copy("template/build.sh", f"recipes/m2-{pkg}/build.sh")
    shutil.copy("template/bld.bat", f"recipes/m2-{pkg}/bld.bat")
