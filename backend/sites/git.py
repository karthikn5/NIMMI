"""
Publishing from a Git repository (GitHub or GitLab).

We download the repository as a .zip archive (no git binary, nothing is run) and publish its
static files: the repository root, or a folder such as dist, build or docs. Private repositories
need a read-only access token. Sites that need a build step (npm run build) should commit their
built folder, or be uploaded built.
"""
import re
import tempfile
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

from netsafe import safe_client
from sites.bundle import BundleError

_GITHUB = re.compile(r"^(?:https?://)?(?:www\.)?github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^?#]+))?/?(?:[?#].*)?$", re.I)
_GITLAB = re.compile(r"^(?:https?://)?(?:www\.)?gitlab\.com[/:]((?:[\w.-]+/)+?)([\w.-]+?)(?:\.git)?(?:/-/tree/([^?#]+))?/?(?:[?#].*)?$", re.I)
_SSH = re.compile(r"^git@(github\.com|gitlab\.com):(.+)$", re.I)
_BRANCH = re.compile(r"^[\w./-]{1,100}$")


@dataclass
class Repo:
    host: str  # github | gitlab
    path: str  # owner/name (GitLab: group/sub/name)
    branch: Optional[str]

    @property
    def url(self) -> str:
        return f"https://{self.host}.com/{self.path}"


@dataclass
class Archive:
    file: tempfile.SpooledTemporaryFile
    commit_sha: Optional[str]
    commit_message: Optional[str]


def parse(url: str, branch: Optional[str] = None) -> Repo:
    raw = (url or "").strip()
    ssh = _SSH.match(raw)
    if ssh:
        raw = f"https://{ssh.group(1)}/{ssh.group(2)}"
    m = _GITHUB.match(raw)
    if m:
        repo = Repo("github", f"{m.group(1)}/{m.group(2)}", m.group(3))
    else:
        m = _GITLAB.match(raw)
        if not m:
            raise BundleError("Enter a GitHub or GitLab repository link, like https://github.com/you/your-site")
        repo = Repo("gitlab", f"{m.group(1)}{m.group(2)}", m.group(3))
    chosen = (branch or "").strip() or repo.branch
    if chosen and not _BRANCH.match(chosen):
        raise BundleError("That branch name isn't valid")
    repo.branch = chosen or None
    return repo


def _not_found(repo: Repo, token: Optional[str]) -> BundleError:
    if token:
        return BundleError(f"We couldn't open {repo.url}{f' (branch {repo.branch})' if repo.branch else ''}. "
                           "Check the link, the branch and that the token can read this repository.")
    return BundleError(f"We couldn't find {repo.url}{f' (branch {repo.branch})' if repo.branch else ''}. "
                       "If the repository is private, add an access token.")


async def _commit(client: httpx.AsyncClient, repo: Repo, token: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """The commit being published (best effort: shown in the deploy history)."""
    try:
        if repo.host == "github":
            headers = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})}
            r = await client.get(f"https://api.github.com/repos/{repo.path}/commits/{repo.branch or 'HEAD'}", headers=headers)
            if r.status_code == 200:
                data = r.json()
                return data.get("sha"), (data.get("commit") or {}).get("message", "").split("\n")[0][:300]
        else:
            headers = {"PRIVATE-TOKEN": token} if token else {}
            r = await client.get(f"https://gitlab.com/api/v4/projects/{quote(repo.path, safe='')}/repository/commits/"
                                 f"{quote(repo.branch or 'HEAD', safe='')}", headers=headers)
            if r.status_code == 200:
                data = r.json()
                return data.get("id"), (data.get("title") or "")[:300]
    except (httpx.HTTPError, ValueError):
        pass
    return None, None


async def download(repo: Repo, token: Optional[str], max_bytes: int) -> Archive:
    """The repository at the branch (or its default branch) as a .zip in a temporary file."""
    if repo.host == "github":
        ref = repo.branch or "HEAD"
        if token:
            url, headers = (f"https://api.github.com/repos/{repo.path}/zipball/{quote(ref, safe='/')}",
                            {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        else:
            url, headers = f"https://codeload.github.com/{repo.path}/zip/{quote(ref, safe='/')}", {}
    else:
        url = f"https://gitlab.com/api/v4/projects/{quote(repo.path, safe='')}/repository/archive.zip"
        if repo.branch:
            url += f"?sha={quote(repo.branch, safe='')}"
        headers = {"PRIVATE-TOKEN": token} if token else {}

    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    async with safe_client(timeout=60.0, follow_redirects=True) as client:
        try:
            async with client.stream("GET", url, headers=headers) as r:
                if r.status_code in (401, 403, 404):
                    raise _not_found(repo, token)
                if r.status_code != 200:
                    raise BundleError(f"{repo.host.title()} didn't send the repository (HTTP {r.status_code}). Try again in a minute.")
                size = 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise BundleError(f"That repository is over {max_bytes // (1024 * 1024)} MB. Publish a smaller "
                                          "folder, or upload the built site instead.")
                    spool.write(chunk)
        except httpx.HTTPError:
            raise BundleError(f"We couldn't reach {repo.host.title()}. Try again in a minute.")
        sha, message = await _commit(client, repo, token)
    spool.seek(0)
    return Archive(spool, sha, message)
