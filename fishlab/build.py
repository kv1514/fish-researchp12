"""Build fishlab/kraken.zip -- a FishLab bot package with the engine vendored.

Pure standard library on purpose. The first version shelled out to rsync and
zip, which this machine does not have and a contributor's might not either;
a build script for a package meant to be handed around should not need tools
the package itself does not.

The package must be SELF-CONTAINED: FishLab unzips it and runs `run` with the
working directory set to the package, with no access to this repository. So
fish/ and fish4/ are copied in -- about 1.3 MB of pure Python, well inside the
64 MB zip / 512 MB unpacked / 8192 file limits.

No symlinks, no absolute paths, no `..`: all are refused by the installer, and
for a good reason -- a symlink is how an archive reaches outside the directory
it was told to unpack into. This asserts the property rather than trusting it.

    py fishlab/build.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "kraken.zip"

TOP = "kraken"                      # zip -r style: one directory at the root
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}
SKIP_SUFFIX = {".pyc", ".pyo"}
SKIP_NAMES = {".DS_Store"}


def _files():
    for name in ("fishbot.json", "bot.py", "README.md"):
        yield HERE / name, f"{TOP}/{name}"
    for pkg in ("fish", "fish4"):
        base = ROOT / pkg
        for p in sorted(base.rglob("*")):
            if p.is_dir() or p.is_symlink():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix in SKIP_SUFFIX or p.name in SKIP_NAMES:
                continue
            yield p, f"{TOP}/{p.relative_to(ROOT).as_posix()}"


def main() -> int:
    manifest = json.loads((HERE / "fishbot.json").read_text())
    assert manifest["format"] == "fishlab-bot/1", manifest["format"]
    assert not Path(manifest["run"][0]).is_absolute(), "run[0] must not be absolute"
    assert ".." not in "/".join(manifest["run"]), "run must not contain .."

    OUT.unlink(missing_ok=True)
    n = total = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in _files():
            if src.is_symlink():
                raise SystemExit(f"refusing to package a symlink: {src}")
            z.write(src, arc)
            n += 1
            total += src.stat().st_size

    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
        bad = [x for x in names
               if x.startswith("/") or ".." in x.split("/")
               or x.startswith("__MACOSX/")]
        assert not bad, f"unsafe entries: {bad[:5]}"
        assert f"{TOP}/fishbot.json" in names, "manifest missing from the zip"
        assert f"{TOP}/fish/cards.py" in names, "engine missing from the zip"
        assert len(names) <= 8192, f"{len(names)} files, limit 8192"
        assert total <= 512_000_000, "over the unpacked limit"
        assert OUT.stat().st_size <= 64_000_000, "over the zip limit"

    print(f"built {OUT.name}: {n} files, {total/1e6:.1f} MB unpacked, "
          f"{OUT.stat().st_size/1e6:.1f} MB zipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
