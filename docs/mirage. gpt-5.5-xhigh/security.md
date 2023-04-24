# Mirage Security Review

All citations refer to `research/mirage` at pinned upstream commit `8b99fb9247ecb40725d4718bac58e3bb230aad34` (`v0.0.1`).

## Scope

This is a static review of the vendored `v0.0.1` source. No Mirage code, tests, examples, package managers, dependency installers, or build steps were executed. Findings below are from code inspection rather than public CVE/OSV/Dependabot output.

## Security Summary

Mirage is alpha-stage infrastructure for agent-facing data access. Its highest-risk area is the daemon: it exposes workspace creation, execution, snapshots, restore, job control, and shutdown without server-side authentication, while workspace commands can read and write mounted resources. The default CLI daemon binds to `127.0.0.1`, which narrows exposure, but any local process can still drive the daemon.

## Findings

### High: Daemon Authentication Is Client-Side Only

The FastAPI app registers all routers directly and has no authentication middleware or dependency guard in `build_app()` (`research/mirage/python/mirage/server/app.py:116`-`research/mirage/python/mirage/server/app.py:129`). The execute endpoint schedules and runs arbitrary workspace commands for any caller that knows the workspace ID (`research/mirage/python/mirage/server/routers/execute.py:93`-`research/mirage/python/mirage/server/routers/execute.py:136`), and the shutdown endpoint sets the daemon exit event without authorization (`research/mirage/python/mirage/server/routers/health.py:41`-`research/mirage/python/mirage/server/routers/health.py:50`).

The CLI has an `auth_token` setting and sends `Authorization: Bearer ...` when present (`research/mirage/python/mirage/cli/settings.py:23`-`research/mirage/python/mirage/cli/settings.py:29`; `research/mirage/python/mirage/cli/client.py:48`-`research/mirage/python/mirage/cli/client.py:55`). It also passes `MIRAGE_AUTH_TOKEN` to the spawned daemon (`research/mirage/python/mirage/cli/client.py:98`-`research/mirage/python/mirage/cli/client.py:105`), but the server factory only reads persist and idle-grace environment variables (`research/mirage/python/mirage/cli/server_factory.py:15`-`research/mirage/python/mirage/cli/server_factory.py:22`). A repository search found no daemon-side bearer-token enforcement under `python/mirage`.

Impact: local untrusted processes can create workspaces, run commands against mounted credentials, download snapshots, delete workspaces, and stop the daemon. If an operator exposes the daemon beyond loopback, this becomes remote unauthenticated command access to whatever resources are mounted.

### High: Snapshot Load Trusts Serialized Resource Class Paths

`POST /v1/workspaces/load` reads the entire uploaded tar and passes it to `Workspace.load()` (`research/mirage/python/mirage/server/routers/workspaces.py:122`-`research/mirage/python/mirage/server/routers/workspaces.py:151`). Snapshot loading builds mounts by calling `_construct_resource()` for non-overridden mounts (`research/mirage/python/mirage/workspace/snapshot/state.py:118`-`research/mirage/python/mirage/workspace/snapshot/state.py:123`). `_construct_resource()` imports a module and class from the serialized `resource_class` field, then instantiates it with config from the snapshot (`research/mirage/python/mirage/workspace/snapshot/state.py:293`-`research/mirage/python/mirage/workspace/snapshot/state.py:315`).

The tar reader validates blob paths and avoids filesystem extraction (`research/mirage/python/mirage/workspace/snapshot/tar_io.py:58`-`research/mirage/python/mirage/workspace/snapshot/tar_io.py:75`; `research/mirage/python/mirage/workspace/snapshot/utils.py:20`-`research/mirage/python/mirage/workspace/snapshot/utils.py:37`), but it does not constrain `resource_class` to the resource registry. Impact depends on importable modules/classes in the process, but the design treats untrusted snapshot metadata as code-loading instructions. Combined with the unauthenticated daemon load endpoint, this is a high-risk trust boundary.

### Medium: SSH Host Key Verification Is Disabled By Default

`SSHConfig.known_hosts` defaults to `None` (`research/mirage/python/mirage/resource/ssh/ssh.py:67`-`research/mirage/python/mirage/resource/ssh/ssh.py:78`). `_connect_kwargs()` passes that `None` value to AsyncSSH when no known-hosts file is configured (`research/mirage/python/mirage/core/ssh/_client.py:43`-`research/mirage/python/mirage/core/ssh/_client.py:58`), and `SSHAccessor.sftp()` uses those kwargs directly in `asyncssh.connect()` (`research/mirage/python/mirage/accessor/ssh.py:28`-`research/mirage/python/mirage/accessor/ssh.py:33`).

Impact: SSH resource traffic can be vulnerable to machine-in-the-middle attacks unless callers explicitly set `known_hosts`. This is especially important because the SSH resource is a read/write remote filesystem mount.

### Medium: Sensitive Data Is Persisted In History, Observer Logs, And Snapshots

`Workspace._record_execution()` stores command, stdout, stdin bytes, exit code, execution tree, timestamp, and session ID in history (`research/mirage/python/mirage/workspace/workspace.py:447`-`research/mirage/python/mirage/workspace/workspace.py:479`). `ExecutionHistory.append()` can persist records as JSONL (`research/mirage/python/mirage/workspace/history.py:21`-`research/mirage/python/mirage/workspace/history.py:42`). The observer writes command/op records into session JSONL files (`research/mirage/python/mirage/observe/observer.py:54`-`research/mirage/python/mirage/observe/observer.py:91`).

Snapshots include cache entries, history records, and finished jobs (`research/mirage/python/mirage/workspace/snapshot/state.py:53`-`research/mirage/python/mirage/workspace/snapshot/state.py:86`). Snapshot persistence writes per-workspace tar files to the configured persist directory without encryption or permission hardening in code (`research/mirage/python/mirage/server/persist.py:70`-`research/mirage/python/mirage/server/persist.py:103`).

Impact: secrets or private data printed by commands, passed through stdin, cached from remote sources, or written to logs can be captured at rest. Resource configs redact some credentials, but operational data and command outputs are not redacted.

### Medium: Daemon Request And Job Paths Lack Resource Limits

The execute router reads multipart `stdin` fully into memory and reads JSON bodies without a code-level size cap (`research/mirage/python/mirage/server/routers/execute.py:139`-`research/mirage/python/mirage/server/routers/execute.py:166`). Workspace history materializes stdout before storing records (`research/mirage/python/mirage/workspace/workspace.py:465`-`research/mirage/python/mirage/workspace/workspace.py:477`), while cache snapshots serialize byte blobs (`research/mirage/python/mirage/workspace/snapshot/manifest.py:63`-`research/mirage/python/mirage/workspace/snapshot/manifest.py:83`). The `sleep` builtin accepts arbitrary duration and awaits it directly (`research/mirage/python/mirage/workspace/executor/builtins.py:681`-`research/mirage/python/mirage/workspace/executor/builtins.py:692`).

Impact: an unauthenticated local caller can create long-running jobs, large stdin payloads, large cached reads, or large snapshots. This is primarily availability risk.

### Low: Cross-Mount Grep Uses Python Regex Without Timeout

Cross-mount `grep`/`rg` compiles user input with `re.compile()` and searches each decoded line without a regex timeout (`research/mirage/python/mirage/workspace/executor/cross_mount.py:172`-`research/mirage/python/mirage/workspace/executor/cross_mount.py:187`). Impact is CPU denial of service with catastrophic-backtracking patterns over large mounted files.

## Positive Controls Observed

- YAML configs use `yaml.safe_load()` and Pydantic models with `extra="forbid"` on cache, mount, and workspace config models (`research/mirage/python/mirage/config.py:103`-`research/mirage/python/mirage/config.py:154`; `research/mirage/python/mirage/config.py:209`-`research/mirage/python/mirage/config.py:236`).
- Disk resource path resolution uses `.resolve()` and `relative_to(root)` before read/write, blocking direct path traversal outside the configured root (`research/mirage/python/mirage/core/disk/read.py:26`-`research/mirage/python/mirage/core/disk/read.py:30`; `research/mirage/python/mirage/core/disk/write.py:25`-`research/mirage/python/mirage/core/disk/write.py:29`).
- Snapshot tar blob references reject empty paths, absolute paths, `..`, and NUL bytes (`research/mirage/python/mirage/workspace/snapshot/utils.py:20`-`research/mirage/python/mirage/workspace/snapshot/utils.py:37`).
- S3, Slack, Gmail, and Postgres snapshot states redact credential fields and require overrides for those mounts (`research/mirage/python/mirage/resource/s3/s3.py:113`-`research/mirage/python/mirage/resource/s3/s3.py:128`; `research/mirage/python/mirage/resource/slack/slack.py:49`-`research/mirage/python/mirage/resource/slack/slack.py:60`; `research/mirage/python/mirage/resource/gmail/gmail.py:51`-`research/mirage/python/mirage/resource/gmail/gmail.py:62`; `research/mirage/python/mirage/resource/postgres/postgres.py:47`-`research/mirage/python/mirage/resource/postgres/postgres.py:58`).

## Security Checklist

| Question | Answer |
| --- | --- |
| Authentication and authorization model | Embedded use inherits the host app's model. The daemon has no server-side auth/authorization in inspected code. CLI bearer token support is not enforced by the server. Mount permissions are coarse `read`/`write`/`exec` flags (`research/mirage/python/mirage/types.py:50`-`research/mirage/python/mirage/types.py:53`). |
| Trust boundaries and validation | Boundaries are workspace config, daemon HTTP inputs, snapshot tar uploads, mounted remote APIs, FUSE syscalls, and optional native execution. Config validation is relatively strong; snapshot class loading and daemon auth are weak. |
| Secrets and credential handling | Config supports `${VAR}` interpolation (`research/mirage/python/mirage/config.py:44`-`research/mirage/python/mirage/config.py:89`) and several resources redact credentials in snapshots, but history/cache/observer data are not redacted. |
| Multi-tenant or multi-user isolation | No real multi-tenant model. Workspace IDs are registry keys; the daemon registry is process-local and unauthenticated. Mount mode controls writes per mount, not per user or source ACL. |
| Encryption at rest and in transit | At rest: no encryption in RAM/Redis cache, history JSONL, snapshots, or persist dir code. In transit: daemon defaults to HTTP loopback (`research/mirage/python/mirage/cli/settings.py:20`; `research/mirage/python/mirage/cli/client.py:105`-`research/mirage/python/mirage/cli/client.py:115`); remote SDKs rely on backend libraries. SSH host verification is disabled unless configured. |
| Logging surface | History and observer logs store command text, stdin/stdout/stderr, session IDs, and operation records. This can include sensitive data. |
| Patch/release cadence and response history | Local vendored Git metadata shows one tag (`v0.0.1`) and three commits through the pinned ref. `SECURITY.md` declares `0.0.x` supported and says reports should be acknowledged within 48 hours, with weekly updates and critical fixes within 7 days (`research/mirage/SECURITY.md:3`-`research/mirage/SECURITY.md:33`). No historical response record is present in the vendored repo. |
| Own scan findings not in public feeds | The daemon auth gap, snapshot dynamic import, SSH known-host default, sensitive history/snapshot persistence, unbounded request/job paths, and regex DoS are findings from static code review. |

## Security Recommendation

Do not run Mirage's daemon in a shared or remotely reachable environment without adding authentication, authorization, request limits, snapshot allowlisting, and safer SSH defaults. For any downstream use, prefer embedded mode inside a trusted host process until daemon hardening exists.

