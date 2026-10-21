"""
Turning an upload (a .zip, a dropped folder's files, or a Git archive) into a site's files, safely.

- Paths that try to leave the site (../, absolute paths, symlinks) reject the whole upload.
- Sizes are checked before and while reading, so a small zip can't expand into gigabytes.
- Secrets and junk are left out: .env files, private keys, .git, node_modules, OS litter.
- Program files (.exe, .apk, ...) aren't published.
- The site's root is found for the user: a zipped folder ("my-site/index.html"), a Git archive's
  top folder, or a build folder (dist, build, out, public, ...) holding index.html.
"""
import hashlib
import posixpath
import re
import stat
import zipfile
from dataclasses import dataclass, field
from typing import BinaryIO, Iterable, Optional

from plans import Limits

SKIP_DIRS = {".git", ".github", ".gitlab", ".svn", ".hg", "node_modules", "__MACOSX", ".idea", ".vscode", ".cache", ".next", ".nuxt",
             ".vercel", ".netlify", "__pycache__", ".venv", "venv"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".gitignore", ".gitattributes", ".gitmodules", ".npmrc", ".netrc", ".htpasswd", "id_rsa", "id_ed25519"}
SECRET = re.compile(r"^\.env(\..*)?$|\.(pem|key|p12|pfx|keystore|jks)$", re.I)
PROGRAMS = re.compile(r"\.(exe|msi|dll|bat|cmd|com|scr|ps1|vbs|jar|apk|aab|dmg|pkg|deb|rpm|sh|bin|iso)$", re.I)
BUILD_DIRS = ("dist", "build", "out", "public", "_site", "site", "www", "docs", "html")


class BundleError(ValueError):
    """A problem with the upload, worded for the person who uploaded it."""


@dataclass
class Bundle:
    files: dict[str, bytes]
    skipped: list[str] = field(default_factory=list)
    spa: bool = False
    commit_sha: Optional[str] = None  # Git: the commit published
    commit_message: Optional[str] = None

    @property
    def total_bytes(self) -> int:
        return sum(len(b) for b in self.files.values())

    def manifest(self) -> dict[str, list]:
        """{path: [sha256, size]}, what a deploy records."""
        return {path: [hashlib.sha256(data).hexdigest(), len(data)] for path, data in self.files.items()}

    def note(self) -> Optional[str]:
        if not self.skipped:
            return None
        shown = ", ".join(sorted(set(self.skipped))[:4])
        more = len(set(self.skipped)) - 4
        return f"Left out {len(self.skipped)} file{'s' if len(self.skipped) != 1 else ''} ({shown}{f' and {more} more' if more > 0 else ''})"


def mb(n: int) -> str:
    return f"{n / (1024 * 1024):.0f} MB"


def clean_path(raw: str) -> str:
    """A safe relative path inside the site, or BundleError for one that tries to escape it."""
    path = (raw or "").replace("\\", "/").strip()
    if not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path) or "\x00" in path:
        raise BundleError("The upload contains a file path we can't accept")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise BundleError("The upload contains a file path that points outside the site")
    if len(path) > 400 or any(len(p) > 200 for p in parts):
        raise BundleError("A file name in the upload is too long")
    return "/".join(parts)


def _skip_reason(path: str) -> Optional[str]:
    parts = path.split("/")
    name = parts[-1]
    if any(p in SKIP_DIRS for p in parts[:-1]) or name in SKIP_NAMES:
        return name if name in SKIP_NAMES else next(p for p in parts[:-1] if p in SKIP_DIRS)
    if SECRET.search(name) or PROGRAMS.search(name):
        return name
    return None


def _strip_prefix(files: dict[str, bytes], prefix: str) -> dict[str, bytes]:
    cut = len(prefix) + 1
    return {p[cut:]: d for p, d in files.items() if p.startswith(prefix + "/")}


def _find_root(files: dict[str, bytes], folder: Optional[str]) -> dict[str, bytes]:
    if folder:
        folder = clean_path(folder)
        # A Git archive has one top folder (repo-branch/); the folder the user named is inside it.
        tops = {p.split("/", 1)[0] for p in files}
        if len(tops) == 1 and not any(p.startswith(folder + "/") for p in files):
            files = _strip_prefix(files, tops.pop())
        inside = _strip_prefix(files, folder)
        if not inside:
            raise BundleError(f"There's no folder called {folder} in it")
        files = inside
    # A zipped folder, or a Git archive: everything under one top folder.
    for _ in range(2):
        tops = {p.split("/", 1)[0] for p in files}
        if "index.html" in files or len(tops) != 1 or all("/" not in p for p in files):
            break
        files = _strip_prefix(files, tops.pop())
    if "index.html" in files:
        return files
    for d in BUILD_DIRS:
        if f"{d}/index.html" in files:
            return _strip_prefix(files, d)
    if "package.json" in files:
        raise BundleError("This looks like source code, not a built site. Build it first (for example npm run build) "
                          "and upload the folder it makes, such as dist or build.")
    raise BundleError("We couldn't find an index.html page. Upload the folder that has your index.html in it.")


def _finish(raw: dict[str, bytes], skipped: list[str], lim: Limits, folder: Optional[str] = None) -> Bundle:
    files = _find_root(raw, folder)
    if len(files) > lim.deploy_files:
        raise BundleError(f"That's {len(files):,} files; your plan allows {lim.deploy_files:,} per deployment")
    total = sum(len(d) for d in files.values())
    if total > lim.deploy_bytes:
        raise BundleError(f"That's {mb(total)}; your plan allows {mb(lim.deploy_bytes)} per deployment")
    pages = [p for p in files if p.lower().endswith((".html", ".htm"))]
    scripts = any(p.lower().endswith((".js", ".mjs")) for p in files)
    return Bundle(files=files, skipped=skipped, spa=len(pages) == 1 and scripts)


def from_zip(fileobj: BinaryIO, lim: Limits, folder: Optional[str] = None, allowance: Optional[int] = None) -> Bundle:
    """Read a .zip. `allowance` is the most it may hold before choosing the root (a Git archive also
    carries source files that aren't published)."""
    allowance = allowance or lim.deploy_bytes
    try:
        archive = zipfile.ZipFile(fileobj)
    except (zipfile.BadZipFile, OSError):
        raise BundleError("That isn't a valid .zip file")
    raw: dict[str, bytes] = {}
    skipped: list[str] = []
    with archive:
        entries = [i for i in archive.infolist() if not i.is_dir()]
        if len(entries) > max(lim.deploy_files * 5, 5000):
            raise BundleError(f"That .zip has {len(entries):,} files, too many to publish")
        if sum(i.file_size for i in entries) > allowance:
            raise BundleError(f"That .zip unpacks to more than your plan's {mb(allowance)}")
        read = 0
        for info in entries:
            if info.flag_bits & 0x1:
                raise BundleError("That .zip is password-protected. Upload it without a password.")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise BundleError("That .zip contains links to other files, which we can't publish")
            path = clean_path(info.filename)
            reason = _skip_reason(path)
            if reason:
                skipped.append(reason)
                continue
            if info.file_size > lim.file_bytes:
                raise BundleError(f"{posixpath.basename(path)} is {mb(info.file_size)}; files can be up to {mb(lim.file_bytes)}")
            with archive.open(info) as f:
                data = f.read(lim.file_bytes + 1)  # never trust the sizes a zip declares
            read += len(data)
            if len(data) > lim.file_bytes or read > allowance:
                raise BundleError(f"That .zip unpacks to more than your plan allows ({mb(allowance)})")
            raw[path] = data
    if not raw:
        raise BundleError("That .zip has no files we can publish")
    return _finish(raw, skipped, lim, folder)


def from_files(items: Iterable[tuple[str, bytes]], lim: Limits) -> Bundle:
    """A dropped or chosen folder: (relative path, contents) pairs."""
    raw: dict[str, bytes] = {}
    skipped: list[str] = []
    total = 0
    for name, data in items:
        path = clean_path(name)
        reason = _skip_reason(path)
        if reason:
            skipped.append(reason)
            continue
        if len(data) > lim.file_bytes:
            raise BundleError(f"{posixpath.basename(path)} is {mb(len(data))}; files can be up to {mb(lim.file_bytes)}")
        total += len(data)
        if total > lim.deploy_bytes:
            raise BundleError(f"Those files are more than your plan's {mb(lim.deploy_bytes)} per deployment")
        raw[path] = data
    if not raw:
        raise BundleError("There are no files to publish")
    return _finish(raw, skipped, lim)
