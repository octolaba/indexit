# Mirage v0.0.1 — Security review

> Run: `claude-opus-4.7-xhigh` · Pinned ref: tag `v0.0.1`, commit
> `8b99fb9247ecb40725d4718bac58e3bb230aad34` · Submodule:
> `research/mirage/`

This is a code-level review, not a re-statement of public CVE/OSV
output. All claims cite a path inside `research/mirage/` at the pinned
commit. Severities follow the rough scale **Critical / High / Medium /
Low / Info**, weighted by exploitability **assuming the daemon is
reachable** — which is the project's stated intent.

## 1. Summary

* `v0.0.1` is **0.0.1-alpha.1**, "Development Status :: 3 - Alpha"
  (`research/mirage/python/pyproject.toml:25`). Three commits in the
  repository, one tag (`v0.0.1`). The security posture matches that
  maturity: lots of capable I/O surfaces, very little defense in depth.
* The single most important fact: **the HTTP daemon (`mirage daemon`)
  has authentication wired into the CLI client but never enforced on
  the server side.** Combined with the fact that the daemon also
  exposes a privileged "shell on the host" path, this is functionally a
  remote code-execution surface that is only mitigated by the default
  loopback bind.
* Path-traversal defenses on **runtime disk ops** are correct
  (`_resolve(root, path).resolve()` + `relative_to(root)`), but the
  **snapshot loader** bypasses them — a crafted snapshot tar gives
  arbitrary file write outside the disk mount root.
* SSH host-key verification is **off by default**: `known_hosts=None`
  is forwarded to `asyncssh.connect`, which means "skip checking".
* Tar reader uses `getmember` + `extractfile`, not `extractall`, and
  blob refs are validated by `is_safe_blob_path` — so the classic
  CVE-2007-4559 surface is closed at the tar layer.
* Snapshot exporter for `DiskResource` reads **every file under
  `root`**, then ships it in the tar. With finding §3.1 + §3.8, that is
  unauthenticated bulk exfiltration of a Disk-mounted directory.

The findings below are listed in **descending severity**. Each has file
+ line cites and a recommended fix.

## 2. Risk register

| #    | Severity     | Title                                                                                 |
| ---- | ------------ | ------------------------------------------------------------------------------------- |
| 3.1  | **Critical** | Daemon HTTP API is unauthenticated despite client-side token plumbing                 |
| 3.2  | **High**     | `POST /v1/.../execute` with `native: true` runs arbitrary shell on the daemon host    |
| 3.3  | **High**     | `POST /v1/shutdown` is unauthenticated → DoS                                          |
| 3.4  | **High**     | Path traversal in `DiskResource.load_state` via crafted snapshot                      |
| 3.5  | **High**     | SSH host-key verification disabled by default (`known_hosts=None`)                    |
| 3.6  | **Medium**   | Snapshot loader imports an attacker-named module via `importlib.import_module`        |
| 3.7  | **Medium**   | `load_backend_class("./script.py:Cls")` → arbitrary Python via file-path spec         |
| 3.8  | **Medium**   | Snapshot endpoint exfiltrates Disk/RAM mount content                                  |
| 3.9  | **Medium**   | `subprocess.run(["fusermount", "-u", mountpoint])` accepts caller-controlled path     |
| 3.10 | **Low**      | SSH `identity_file` path is not redacted in snapshots                                 |
| 3.11 | **Low**      | `daemon.pid` file written without locking; concurrent daemons                         |
| 3.12 | **Low**      | `daemon.log` grows unbounded (no rotation)                                            |
| 3.13 | **Low**      | Observer JSONL captures verbatim stdin / stdout / commands                            |
| 3.14 | **Low**      | `GitHubResource.__init__` does synchronous network I/O on the daemon's request thread |
| 3.15 | **Info**     | Tar reader and `is_safe_blob_path` correctly defend the tar layer                     |
| 3.16 | **Info**     | Disk-resource runtime ops correctly enforce `relative_to(root)`                       |

## 3. Findings (detail)

### 3.1. **Critical** — Daemon has no authentication

**Where.**
* `research/mirage/python/mirage/cli/server_factory.py:15-22`
* `research/mirage/python/mirage/server/app.py:92-130`
* `research/mirage/python/mirage/cli/client.py:48-127`
* `research/mirage/python/mirage/cli/settings.py:20-74`

**What I found.** The client is wired with auth tokens:

```python
# research/mirage/python/mirage/cli/client.py:48-51
def _headers(self) -> dict[str, str]:
    if self.settings.auth_token:
        return {"Authorization": f"Bearer {self.settings.auth_token}"}
    return {}
```

```python
# research/mirage/python/mirage/cli/client.py:98-117
def _spawn_daemon(self) -> None:
    ...
    if self.settings.auth_token:
        env["MIRAGE_AUTH_TOKEN"] = self.settings.auth_token
    cmd = [..., "uvicorn", "mirage.cli.server_factory:app", "--host",
           "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    subprocess.Popen(cmd, env=env, ...)
```

The settings module reads `MIRAGE_TOKEN` and propagates it to
`MIRAGE_AUTH_TOKEN` for the spawned daemon. **The daemon never reads
that variable**:

```python
# research/mirage/python/mirage/cli/server_factory.py:15-22
import os
from mirage.server import build_app

_persist_dir = os.environ.get("MIRAGE_PERSIST_DIR") or None
_idle_grace = float(os.environ.get("MIRAGE_IDLE_GRACE_SECONDS", "30"))

app = build_app(idle_grace_seconds=_idle_grace, persist_dir=_persist_dir)
```

`build_app` registers the routers with **no `Depends(...)`, no
authentication middleware, no token check** anywhere
(`research/mirage/python/mirage/server/app.py:92-130`).
`grep -RIn "MIRAGE_AUTH_TOKEN\|Authorization\|Bearer\|Depends.*auth"`
inside `python/mirage/server/` returns **zero hits**. The headers a
client sends are simply discarded.

**Impact.** Any HTTP client that can reach the bind address can:
* Create or delete arbitrary workspaces and mount any registered
  resource with attacker-supplied credentials
  (`POST /v1/workspaces`, `DELETE /v1/workspaces/{id}` —
  `routers/workspaces.py:36-75`).
* Execute arbitrary shell commands inside any workspace, including the
  privileged `native: true` path (see §3.2).
* Snapshot any workspace (§3.8) and ingest a tarball that the daemon
  will then auto-rehydrate on next start (§3.4 + §3.6).
* Trip `POST /v1/shutdown` to stop the daemon (§3.3).

**Mitigations in v0.0.1.** Two only:
1. The CLI auto-spawn forces `--host 127.0.0.1`
   (`cli/client.py:106-111`). On a single-user box this isolates the
   daemon to the local UID via TCP loopback (still readable by any
   process running as the same user).
2. `MIRAGE_DAEMON_URL` overrides the URL the *client* uses, but the
   *daemon* binds wherever its uvicorn invocation tells it to. Anyone
   running `uvicorn mirage.cli.server_factory:app --host 0.0.0.0`,
   port-forwarding the loopback port, or running Mirage inside a
   container exposed to a network — gets full unauth.

**Fix.** Read `MIRAGE_AUTH_TOKEN` in `server_factory.py`, install a
FastAPI dependency that compares against the token, and apply it to all
routers except `/v1/health`. Treat the token as a shared secret only —
do not lean on it for multi-tenant separation; it is currently impossible
in v0.0.1 (no per-token authorization scope).

### 3.2. **High** — Native exec is raw `subprocess_shell`

**Where.** `research/mirage/python/mirage/workspace/native.py:20-42`,
called from `Workspace.execute(..., native=True)`
(`research/mirage/python/mirage/workspace/workspace.py:489-499`),
exposed via `POST /v1/.../execute?native=true`
(`research/mirage/python/mirage/server/routers/execute.py:29-167`).

```python
# workspace/native.py:26-32
proc = await asyncio.create_subprocess_shell(
    command,
    cwd=str(cwd),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=env,
)
```

**What this is.** A raw shell pipeline, no allowlist, no escaping, no
sandbox, no `seccomp`/`pledge`. The cwd is the FUSE mountpoint
(`workspace.py:497`), which still keeps the spawned shell rooted at the
host filesystem from `/`.

**Impact.** Combined with §3.1, this is the most direct RCE path: an
unauth caller submits `{"command": "curl … | sh", "native": true}` and
gets shell on the daemon host as the daemon user.

**Why mention it as a separate finding.** Even with auth in place
(§3.1), `native=true` is a strictly more powerful capability than the
virtual-VFS path. Any future authorization model must be able to gate
`native` independently. Today, anyone allowed to call `execute` is
allowed to call `execute` with `native: true`.

**Fix.** (a) Make `native` opt-in at workspace creation time, off by
default and impossible to turn on per-request. (b) Require a separate
permission token / scope. (c) Document loudly — the README pitches
"familiar bash tools" as virtual; the native path is the literal real
shell.

### 3.3. **High** — `POST /v1/shutdown` is unauthenticated

**Where.** `research/mirage/python/mirage/server/routers/health.py:41-50`.

```python
@router.post("/v1/shutdown", response_model=ShutdownResponse)
async def shutdown(request: Request) -> ShutdownResponse:
    request.app.state.exit_event.set()
    return ShutdownResponse(status="shutting_down", pid=os.getpid())
```

**Impact.** Anyone reachable can DoS the daemon. With persistence
disabled, all in-RAM workspaces are lost (history, RAM mounts, jobs).

**Fix.** Same as §3.1 — bind the auth dependency to this route.

### 3.4. **High** — Path traversal in `DiskResource.load_state`

**Where.** `research/mirage/python/mirage/resource/disk/disk.py:103-108`.

```python
def load_state(self, state: dict) -> None:
    files = state.get("files", {})
    for rel, data in files.items():
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
```

**Why it's exploitable.** The reverse direction — runtime disk ops —
defends correctly: every op funnels through `_resolve(root, path)` and
`resolved.relative_to(root)` raises if the resolved path leaves the
mount (verified across
`research/mirage/python/mirage/core/disk/{read,write,unlink,mkdir,rmdir,rename,truncate,append,copy,find,du,exists,readdir,stat,stream,rm,create}.py`).
The snapshot loader does **not** apply that check on the dictionary
keys it receives from the manifest.

The tar layer cannot save us either: `is_safe_blob_path` filters the
**tar entry name** that holds the bytes
(`research/mirage/python/mirage/workspace/snapshot/utils.py:20-37`),
not the **mapping key** inside `state["files"]`. The snapshot writer
generates safe blob filenames server-side
(`research/mirage/python/mirage/workspace/snapshot/manifest.py:96-101`),
but the *manifest mapping key* `rel` flows through unfiltered.

**Exploit path.** With §3.1 + `POST /v1/workspaces/load` accepting an
attacker-uploaded tar
(`research/mirage/python/mirage/server/routers/workspaces.py:122-167`):

```json
{
  "mounts": [{
    "prefix": "/disk/",
    "resource_class": "mirage.resource.disk.disk.DiskResource",
    "resource_state": {
      "type": "disk",
      "files": {
        "../../../../etc/cron.d/mirage": "<blob ref>"
      }
    }
  }]
}
```

`DiskResource(root="/tmp/x")` constructed by `_construct_resource`
auto-mints a fresh `tempfile.mkdtemp` root
(`research/mirage/python/mirage/workspace/snapshot/state.py:300-303`).
`load_state` then walks the file map and writes
`/tmp/x/../../../../etc/cron.d/mirage` → outside the root, anywhere the
daemon UID can reach.

**Fix.** Reuse `_resolve(self.root, rel)` in `load_state`; reject any
key whose resolved path is not `relative_to(self.root)`. Identical fix
applies to the TS sibling.

### 3.5. **High** — SSH host-key verification disabled by default

**Where.** `research/mirage/python/mirage/core/ssh/_client.py:53-62`.

```python
if config.known_hosts is not None:
    kwargs["known_hosts"] = config.known_hosts
else:
    kwargs["known_hosts"] = None
...
return await asyncssh.connect(**_connect_kwargs(config))
```

**Why it matters.** In `asyncssh.connect`, `known_hosts=None` means
**accept any host key**. There is no `~/.ssh/known_hosts` fallback and
no `~/.ssh/config` consultation. `SSHConfig.known_hosts` defaults to
`None` (`research/mirage/python/mirage/resource/ssh/ssh.py:67-77`).

**Impact.** Every SSH connection Mirage makes is MITM-able by anyone on
the network path between the daemon and the SSH host. Credentials sent
over channel (private-key auth via `client_keys=[identity_file]`,
line 56-57) are not exposed, but the *target* of those credentials is —
an attacker can intercept the session, transparently re-encrypt to the
real server, and silently rewrite SFTP traffic.

**Fix.** Default to `os.path.expanduser("~/.ssh/known_hosts")` when
`config.known_hosts is None`. Refuse connection if neither the user's
file nor an explicit value is provided. Mirror the fix in TS.

### 3.6. **Medium** — Snapshot loader imports an attacker-named module

**Where.** `research/mirage/python/mirage/workspace/snapshot/state.py:293-326`.

```python
def _construct_resource(mount_state: dict):
    cls_path = mount_state[MountKey.RESOURCE_CLASS]
    mod_name, cls_name = cls_path.rsplit(".", 1)
    cls = getattr(importlib.import_module(mod_name), cls_name)
    ...
    if ptype == ResourceName.RAM:
        return cls()
```

**Why it's a risk.** `importlib.import_module(mod_name)` runs the
target module's top-level code as a side effect. The `mod_name`
comes from the manifest, which means an attacker controlling the
uploaded tar (§3.4 prerequisite) can name *any importable module
present in the daemon's environment*. Stdlib modules (`os`, `subprocess`,
`pathlib`) are safe — their import is a no-op. Third-party modules
that do work at import time (telemetry beacons, license callbacks,
etc.) are not. While the second `cls()` call is gated by
`ResourceName.RAM`, the import has already happened.

**Impact.** Limited unless the daemon image happens to include a
package whose import-time behaviour is dangerous. Useful as a
fingerprinting / stack-disclosure primitive even in benign cases.

**Fix.** Validate `mod_name` against the project's `REGISTRY`
(`resource/registry.py:28-107`). Reject anything outside it.

### 3.7. **Medium** — `load_backend_class("./script.py:Class")` is `exec_module`

**Where.** `research/mirage/python/mirage/resource/loader.py:34-49`.

```python
if "/" in source or source.endswith(".py"):
    module_spec = importlib.util.spec_from_file_location(
        "_mirage_user_backend", source)
    ...
    module_spec.loader.exec_module(module)
```

**Why it's a risk.** Anyone whose code can make a `build_resource` call
with a script-path spec runs that script as the daemon user. v0.0.1's
HTTP API doesn't surface this (the registry path uses dotted module
names, never a script path), so the exposure today is "anyone authoring
a workspace YAML can inject Python via a path-style `resource:` field"
— which mostly equals "anyone with write access to the YAML can do
what `python` could already do". The danger is that the dispatcher is
*one* unsafe call away from RCE, and it sits behind the same
unauthenticated `POST /v1/workspaces` (§3.1) that already accepts a
`config` block.

**Fix.** Either drop the file-path branch from `load_backend_class`
entirely, or gate it behind a feature flag that is off when the
HTTP API is enabled. Document the trade-off.

### 3.8. **Medium** — Snapshot endpoint exfiltrates Disk/RAM content

**Where.**
* `research/mirage/python/mirage/server/routers/workspaces.py:99-119`
* `research/mirage/python/mirage/resource/disk/disk.py:90-101`
* `research/mirage/python/mirage/workspace/snapshot/manifest.py:85-101`

`DiskResource.get_state()`:

```python
def get_state(self) -> dict:
    files: dict[str, bytes] = {}
    for p in self.root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(self.root).as_posix()
            files[rel] = p.read_bytes()
    return {..., "files": files}
```

**Impact.** A `GET /v1/workspaces/{id}/snapshot` returns a tar that
contains every byte of every file inside the Disk mount root. Combined
with §3.1, that is unauthenticated bulk exfiltration. RAM mounts and
the **file cache** (`workspace/workspace.py:65-118`) get the same
treatment — anything pulled into the cache (e.g., agent reads of S3
objects, GDrive docs) is in the snapshot too
(`workspace/snapshot/state.py:53-86`).

**Fix.** Auth on the endpoint plus an explicit "include cached file
data" flag (default off). For Disk mounts, also support
`include_files=False` so a snapshot can be a *configuration-only*
artifact.

### 3.9. **Medium** — `fusermount -u <mountpoint>` accepts caller path

**Where.** `research/mirage/python/mirage/fuse/mount.py:78-86`.

```python
except KeyboardInterrupt:
    print("\nUnmounting...", flush=True)
    if sys.platform == "darwin":
        subprocess.run(
            ["diskutil", "unmount", "force", mountpoint],
            capture_output=True,
        )
    else:
        subprocess.run(["fusermount", "-u", mountpoint],
                       capture_output=True)
```

`mountpoint` comes from `Workspace.set_fuse_mountpoint(path)`
(`research/mirage/python/mirage/workspace/workspace.py:213-219`), which
is settable via the embed API and indirectly from any code that
constructs the workspace. There is no validation that the path is a
mountpoint that the current user owns.

**Impact.** Not direct command injection (argv list, not `shell=True`),
but a caller can ask the daemon to invoke `diskutil unmount force` /
`fusermount -u` on **any path the daemon UID can reach**. With §3.1
this becomes "unmount arbitrary FUSE mounts the daemon owns". Limited
blast radius; documented as a hygiene improvement.

**Fix.** Compare `mountpoint` against the workspace's own
`_fuse.mountpoint` and refuse if they differ; or validate that
`os.path.realpath(mountpoint)` is inside an allowlist.

### 3.10. **Low** — SSH `identity_file` path leaks in snapshot

**Where.** `research/mirage/python/mirage/resource/ssh/ssh.py:108-119`.

```python
def get_state(self) -> dict:
    redacted = []
    cfg = self.config.model_dump()
    for f in redacted:
        ...
    return {..., "config": cfg}
```

`SSHConfig.identity_file: str | None` is a path on the daemon host
(`research/mirage/python/mirage/resource/ssh/ssh.py:67-77`). It is not
listed in `redacted`, so the snapshot tar carries the absolute path
where the operator's SSH key lives. `needs_override=False` means the
loader doesn't even ask for a fresh value — it just re-uses it.

**Fix.** Mark `identity_file` as redacted, set `needs_override=True`
when present.

### 3.11. **Low** — PID file written without locking

**Where.** `research/mirage/python/mirage/server/app.py:33-47`.

```python
def _write_pid_file() -> None:
    p = _pid_file_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(os.getpid()))
```

No `O_EXCL`, no fcntl lock. Two daemons starting concurrently overwrite
each other; `mirage daemon stop` may then SIGTERM the wrong PID.

**Fix.** Open with `O_CREAT | O_EXCL`. If the file exists, check
`/proc/<pid>` (or `os.kill(pid, 0)`) and either reject or take over
deliberately.

### 3.12. **Low** — `daemon.log` grows unbounded

**Where.** `research/mirage/python/mirage/cli/client.py:117-127`.

```python
log_file = log_dir / "daemon.log"
with open(log_file, "ab") as f:
    subprocess.Popen(cmd, env=env, stdout=f, stderr=subprocess.STDOUT,
                     start_new_session=True)
```

No rotation, no truncate. A long-running daemon eventually fills disk.

**Fix.** Use a rotating handler or rely on systemd journald.

### 3.13. **Low** — Observer JSONL captures verbatim stdin/stdout/commands

**Where.** `research/mirage/python/mirage/observe/observer.py:54-103`,
`research/mirage/python/mirage/workspace/workspace.py:447-479`.

The observer appends every op record and every command record as JSONL
to `<observe_prefix>/<UTC date>/<session>.jsonl`. The default observer
resource is RAM (`research/mirage/python/mirage/workspace/workspace.py:137-141`)
but the docs / DX explicitly suggest persisting it via a Disk-backed
resource for replay. The records include:
* `command` (full shell text)
* `stdin` (raw bytes)
* `stdout` (raw bytes; serialized via `materialize_stdout()`)
* `stderr`

**Why it matters.** If an agent ever runs
`cat /disk/.aws/credentials` or pipes a Slack token through `echo`, the
plaintext lands in the JSONL. With §3.8 / §3.1 the JSONL becomes
exfiltratable.

**Fix.** Either don't record `stdout`/`stderr` by default, or scrub
common secret patterns before writing. At minimum, document the risk in
`SECURITY.md`.

### 3.14. **Low** — `GitHubResource.__init__` does sync network I/O

**Where.** `research/mirage/python/mirage/resource/github/github.py:36-89`.

```python
def __init__(self, config, owner, repo, ref="main"):
    super().__init__()
    default_branch = fetch_default_branch_sync(config, owner, repo)
    tree, truncated = fetch_tree_sync(config, owner, repo, ref)
    ...
```

These calls run synchronously inside `Workspace(__init__)`, which is
itself called from a FastAPI handler running on the WorkspaceRunner's
event loop thread (`server/routers/workspaces.py:36-49`). A slow GitHub
API or rate limit blocks the thread.

**Impact.** Availability only; no confidentiality / integrity loss.

**Fix.** Move the bootstrap into a lazy first-use call, or run it in
a worker thread.

### 3.15. **Info** — Tar reader and blob-path filter are sound

`workspace/snapshot/tar_io.py:58-93` reads via `getmember` +
`extractfile`, never `extractall`. `is_safe_blob_path`
(`workspace/snapshot/utils.py:20-37`) rejects empty strings, leading
`/`, NUL bytes, and any segment equal to `..`. Symlink + hardlink
extraction is not exercised because `_make_reader` only calls
`extractfile`. **The classic CVE-2007-4559 surface is closed at the
tar layer.** The traversal in §3.4 is *higher up* — in the manifest
keys — and is fixable in `DiskResource.load_state` without touching
the tar layer.

### 3.16. **Info** — Disk-resource runtime ops correctly contain paths

Every Disk runtime op uses the same `_resolve(root, path)` shape:

```python
# research/mirage/python/mirage/core/disk/read.py:26-30
def _resolve(root: Path, path: str) -> Path:
    relative = path.lstrip("/")
    resolved = (root / relative).resolve()
    resolved.relative_to(root)   # raises ValueError outside
    return resolved
```

Verified across `read.py`, `write.py`, `unlink.py`, `mkdir.py`,
`rmdir.py`, `rename.py`, `truncate.py`, `append.py`, `copy.py`,
`find.py`, `du.py`, `exists.py`, `readdir.py`, `stat.py`, `stream.py`,
`rm.py`, `create.py`. A symlink that escapes the root via `realpath`
also fails the `relative_to` check because `Path.resolve()` follows
symlinks. **Runtime disk path-traversal: defended.**

## 4. Reviewed-and-no-issues categories

To meet the issue's acceptance criterion ("at least one category is
reported as either a concrete code-level finding or an explicit
'reviewed, no issues found'"):

| Category                                   | Verdict at v0.0.1                                                                                                                                                                                   |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tar `extractall` traversal (CVE-2007-4559) | **Reviewed, no issues** — tar reader does not use `extractall`; per-blob path validated (§3.15)                                                                                                     |
| Disk-resource runtime path traversal       | **Reviewed, no issues** — `_resolve` enforces `relative_to(root)` (§3.16)                                                                                                                           |
| YAML deserialization                       | **Reviewed, no issues** — `yaml.safe_load` is used consistently (`config.py:228`, `cli/workspace.py:32`, `server/persist.py:49`)                                                                    |
| Pickle / `eval` / `exec` of user data      | **No findings** — no `pickle`, `marshal`, `eval`, `exec` of network-sourced data observed in `python/mirage/`; `exec_module` is only called from the `load_backend_class` script-path branch (§3.7) |
| Public CVE / OSV / Dependabot echo         | **Out of scope by design.** Project is alpha; the known surface is everything documented above. No upstream advisories on `mirage-ai 0.0.1` at the pin                                              |

## 5. Authn / authz model (answer to §4.2)

* **Authentication.** None enforced server-side; client-side bearer
  token plumbing is dead code in v0.0.1.
* **Authorization.** None. Every endpoint is "do everything any user
  can". No per-workspace ACL, no scope on tokens (because there are no
  tokens), no rate limit.
* **Trust boundaries.**
  * SDK-embed: the workspace's trust boundary equals the host process's
    trust boundary. The `__enter__` patch of `builtins.open` and
    `sys.modules["os"]` (`workspace.py:254-263`) merges them
    completely.
  * Daemon: the trust boundary is the OS user the daemon runs as. The
    HTTP API treats every caller as that user.
  * FUSE: trust boundary is the OS — anyone with read on the FUSE
    mountpoint can read Mirage's view.
* **Multi-tenant isolation.** Not provided. Workspaces share the same
  daemon process, the same OS user, the same FUSE mountpoint, the same
  cache pools. There is *namespacing* via mount prefixes and
  `workspace_id`, but no isolation.

## 6. Encryption answer to §4.2

* **In transit.** Backend connections are TLS through the upstream
  SDK's defaults: `aioboto3` to S3-compat, `httpx` to GitHub / Linear /
  Notion / Slack / Trello, `asyncssh` for SSH, `motor`/`asyncpg` for
  Mongo/Postgres (TLS depends on the DSN). No `verify=False` overrides
  observed.
* **At rest.** Snapshot tars are written **plaintext** to
  `MIRAGE_PERSIST_DIR` and to whatever path the user passes to
  `Workspace.snapshot(target)`. Disk content, RAM content, and cached
  bytes are stored without encryption.
* **HTTP daemon.** No TLS. The default is plain HTTP on `127.0.0.1`.
  Loopback + same-user is the implicit security boundary.

## 7. Logging answer to §4.2

* **stdlib `logging`** with module-level loggers. No structured fields
  by default.
* **Sensitive content** can land in two places:
  * `daemon.log` (uvicorn stderr/stdout — request paths/methods, no
    bodies by default).
  * Observer JSONL (verbatim `stdout`/`stderr`/`stdin` — see §3.13).
* **Snapshot tars** include the cache file bytes
  (`snapshot/state.py:53-86`); anything cached during the run is in the
  snapshot.

## 8. Patch / release cadence answer to §4.2

* `git log` at the pin shows three commits total
  (`8b99fb9 Update`, `5eb17c3 Update`, `924ec49 Initial public release`)
  and a single tag `v0.0.1`.
* `SECURITY.md` advertises a 48-hour acknowledgement window, weekly
  status updates, 7-day fix target for critical issues, 90-day
  responsible-disclosure window, and a `zecheng@strukto.ai` reporting
  address (`research/mirage/SECURITY.md:1-33`). No advisories published
  yet.
* No GitHub Dependabot config, no `.github/dependabot.yml` in the
  repository at the pin (`find research/mirage/.github -type f` →
  `infra-example.yml`, `pre-commit.yml`, `test.yml` only).

## 9. Recommended remediation order

1. Daemon auth (`MIRAGE_AUTH_TOKEN` enforced server-side) — closes
   §3.1, §3.3, downgrades §3.2/§3.4/§3.6/§3.8/§3.9 from "anyone" to
   "authenticated caller".
2. `DiskResource.load_state` path validation — closes §3.4.
3. SSH `known_hosts` default-on (`~/.ssh/known_hosts` or fail-closed) —
   closes §3.5.
4. Native-exec gating (require explicit per-workspace opt-in) —
   downgrades §3.2.
5. Snapshot endpoint scope flag + observer redaction policy — closes
   §3.8 / §3.13.
6. Resource-class allowlist in `_construct_resource` — closes §3.6.
7. Drop the script-path branch in `load_backend_class` — closes §3.7.
8. SSH config redaction + PID-file lock + log rotation — closes §3.10,
   §3.11, §3.12.
