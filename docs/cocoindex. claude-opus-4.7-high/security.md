# CocoIndex — Security review

| Field         | Value                                                                                                                                                                                                                                           |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Subject       | [cocoindex-io/cocoindex](https://github.com/cocoindex-io/cocoindex)                                                                                                                                                                             |
| Pinned tag    | `v1.0.3`                                                                                                                                                                                                                                        |
| Pinned commit | `4432311228e4859201b457d3b6d978471692d0b1`                                                                                                                                                                                                      |
| Vendored at   | `research/cocoindex/`                                                                                                                                                                                                                           |
| Analyst       | `claude-opus-4.7` (1M-context, effort: high)                                                                                                                                                                                                    |
| Scope         | §3.2 + §4.2 of `CLAUDE.md` / `AGENTS.md`. Static, read-only review. No fuzzing, no execution, no network.                                                                                                                                       |
| Threat model  | Single-user developer or batch operator running CocoIndex against directories, databases, and SaaS sources they own or are authorised to read. **Not** a multi-tenant or hostile-user threat model — CocoIndex does not attempt to provide one. |

> **Frame.** This is the answer to the §4.2 questionnaire plus an
> independent code-level scan beyond CVE/OSV/Dependabot. Where a category
> was reviewed and produced no concrete finding, that is recorded
> explicitly rather than skipped.

## Findings summary

| ID  | Severity¹ | Category                  | Title                                                                         | Status               |
| --- | --------- | ------------------------- | ----------------------------------------------------------------------------- | -------------------- |
| F-1 | Medium    | Path traversal (symlinks) | localfs walker follows symlinks; no allowlist / `realpath` containment check  | New, not in CVE/OSV  |
| F-2 | Low–Med   | Privacy / data egress     | Anonymous usage telemetry POSTs to Scarf gateway by default in release builds | Documented, opt-out  |
| F-3 | Low       | Trust boundary (IPC)      | GPU subprocess uses unrestricted `pickle.loads` over a parent–child pipe      | Trusted-by-design    |
| F-4 | Low       | Sandboxing                | User `@coco.fn` code runs in the host interpreter with no resource limits     | By design            |
| F-5 | Low       | Supply chain              | No `cargo-audit`, `cargo-deny`, or `pip-audit` in CI / pre-commit             | Gap                  |
| F-6 | Info      | Auth surface              | `axum` is in workspace deps but no HTTP server is exposed in v1.0.3           | Dead/scaffolded code |
| F-7 | Info      | State at rest             | LMDB env at `~/.cocoindex` inherits umask only; no application-level ACL      | By design            |

¹ Severities reflect the **default deployment** (single-user developer/batch
operator). They climb in shared / multi-user / untrusted-input contexts.

The following categories were **reviewed and no issues found**: SQL
injection (`§B3-SQL`), insecure TLS (`§B5`), unsafe Rust
(`§B-rust-unsafe`), unsafe YAML (`§B3-yaml`), `eval`/`exec` of untrusted
input (`§B3-eval`), pickle deserialisation of untrusted data when
unrestricted (`§B3-pickle` — `_RestrictedUnpickler` allowlist holds).

## §B1. Authentication & authorisation

**No HTTP server is started by CocoIndex v1.0.3.** The only `axum::serve(...)`
call is inside a `#[cfg(test)]` block that spins up a mock HTTP server for
the telemetry unit tests (rust/core/src/telemetry/mod.rs:166–183). Every other
axum reference is type-only:
* `rust/core/Cargo.toml:35` — workspace dep.
* `rust/utils/Cargo.toml:12` — workspace dep.
* `rust/utils/src/error.rs:1–5` — uses `axum::http::StatusCode`,
  `IntoResponse`, `Response`, and `Json` to scaffold an `ApiError` /
  `IntoResponse` impl. The only consumer is
  `rust/utils/src/prelude.rs:1`, which re-exports it; no caller turns it
  into an HTTP response.

Conclusion: there is no auth surface in v1.0.3. Any "API access control"
discussion in older docs is v0 history, not v1 reality. Recorded as
**F-6** (informational): the axum dependency cost is paid (build time,
bytes in the wheel, dependency-graph attack surface) without producing a
runtime endpoint.

The only outbound network call CocoIndex *itself* originates is the
telemetry POST (see §B7). Everything else (database connections,
embedding APIs, Google Drive, S3, OCI, Kafka) is initiated by user-defined
pipelines using credentials the operator supplies.

## §B2. Trust boundaries

| Boundary                            | Enforcement                                                                                                                                                                      |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User Python module loaded by CLI    | None (`python/cocoindex/_internal/user_app_loader.py` uses `importlib.spec.loader.exec_module`). Treated as fully trusted code.                                                  |
| `@coco.fn` user functions           | None. Run in-process; can do anything the interpreter can. Memoization fingerprint is cache-only, not authorisation.                                                             |
| LMDB state directory (read & write) | Filesystem ACLs only. No application-level integrity tag, no encryption, no MAC. Tampering is detectable only via the restricted unpickler invariant (§B3 / `serde.py:185–195`). |
| Source connector input              | Source-level: pathlib/SQL/SDK; no normalisation across connectors.                                                                                                               |
| Embedding/LLM HTTP responses        | reqwest validates TLS + status; payload is parsed via `serde_json` / numpy with shape checks at the call site.                                                                   |
| Telemetry to Scarf                  | reqwest with rustls; payload is hard-coded fields — no user data, see §B7.                                                                                                       |
| GPU subprocess IPC                  | Local pipe; payload is `pickle`. Trusted because both ends are spawned by the same user.                                                                                         |

Where these boundaries leak in practice: see F-1 (symlinks crossing the
"localfs root" boundary).

## §B3. Input validation, deserialisation, injection

### §B3-yaml — YAML
`grep -rn "yaml.load\|yaml.unsafe_load\|yaml.Loader\|yaml.UnsafeLoader" python/`
returns **no results**. `pyyaml` is not even a runtime dependency.
**Reviewed, no issues found.**

### §B3-eval — `eval` / `exec` of untrusted input
`grep -rn "\beval(\|\bexec(" python/cocoindex/` after filtering
`importlib.exec_module` returns **no results**. The only `exec_module` call
is `python/cocoindex/_internal/user_app_loader.py`, which loads the
operator's own pipeline file — by design and not a finding.
**Reviewed, no issues found.**

### §B3-pickle — pickle deserialisation
Three call sites:
1. **Memoization fingerprinting** — `python/cocoindex/_internal/memo_fingerprint.py:323`
   only calls `pickle.dumps(...)`; never `loads`. Bytes are hashed for cache
   keys, never re-instantiated. No risk.
2. **State / cache deserialisation** — `python/cocoindex/_internal/serde.py:7,128–195`.
   This is the load-bearing one. CocoIndex implements
   `_RestrictedUnpickler(pickle.Unpickler)` whose `find_class()` consults
   an explicit allowlist `_UNPICKLE_SAFE_GLOBALS`. The allowlist is bootstrapped
   from a hard-coded set of built-ins (`bool, int, float, complex, str, bytes,
   bytearray, list, tuple, dict, set, frozenset, NoneType, type` —
   `serde.py:24–40`), the `pathlib`, `uuid`, `datetime` stdlib subtree
   (`serde.py:51–60`), and optional numpy reconstruction helpers
   (`serde.py:67–88`). Custom classes opt in via `@unpickle_safe`
   (`serde.py:128–132`) or `@serialize_by_pickle` (`serde.py:151–162`).
   Unknown globals raise `pickle.UnpicklingError("Forbidden global during
   unpickling: …")` (`serde.py:185–195`). This is **the right design**:
   even if an attacker swapped the on-disk LMDB file or fingerprint blob,
   the payload could only construct allowlisted shapes, not invoke
   arbitrary `__reduce__`.
3. **GPU subprocess IPC** — `python/cocoindex/_internal/runner.py:172–199`.
   `pickle.loads(payload_bytes)` (line 173) and `pickle.loads(result_bytes)`
   (line 199) are unrestricted. **Logged as F-3.** Both ends of the pipe
   are children of the same user, so the realistic threat is a local
   process injecting bytes into the pipe — out of scope for the default
   threat model. Worth tightening only if CocoIndex ever lets the
   subprocess be reached over a network socket.

### §B3-SQL — SQL injection
The Postgres connector uses `asyncpg` with parameterised queries throughout
(`python/cocoindex/connectors/postgres/_target.py`); identifiers are wrapped
through `_qualified_table_name(...)` which double-quotes names. No
`format!()` / f-string composition of values into SQL was found. The Doris
target uses `aiomysql` similarly. **Reviewed, no issues found.**

### §B3-path — Path traversal (filesystem)
`python/cocoindex/connectors/localfs/_source.py` performs the directory walk
that drives most file-source pipelines. Two relevant defences are present:
(a) `entry.relative_to(root_resolved)` is computed and an entry whose
relative form fails is silently skipped (`_source.py:117–121`); (b)
`PermissionError` and `OSError` on individual entries are caught and
skipped (`_source.py:111–113, 134–136`).

**What is not present** is any symlink containment. `Path.iterdir()`,
`Path.is_dir()`, `Path.is_file()`, and `Path.resolve()` all *follow*
symlinks; `is_symlink()`, `lstat`, or a "resolved-target stays inside
root" check would be required to block them. `grep -rn "is_symlink\|symlink\|lstat\|readlink" python/cocoindex/connectors/ python/cocoindex/resources/`
returns no results — confirmed absent.

Concrete consequence:
* A symlink at `<root>/inner/escape` pointing to `/etc/passwd` is reported
  as a regular file; `entry.relative_to(root_resolved)` returns
  `inner/escape` (the symlink path is under `root_resolved`); reading goes
  through `self._file_path.resolve()` (`_source.py:54, 60`), which
  dereferences to `/etc/passwd`. The bytes are then handed to the user
  pipeline and indexed into whatever target the pipeline declares.
* If the watched directory is writeable by an account distinct from the
  CocoIndex operator (e.g. a "drop folder"), this is a straightforward
  exfiltration primitive bounded only by what the CocoIndex process can
  read.

Logged as **F-1**. This is *not* in CVE/OSV/Dependabot — it is a behaviour
of the connector, not a known vulnerable dependency.

### §B3-cmd — Command / shell execution
`grep -rn "subprocess\|os\.system\|shell=True" python/cocoindex/` returns
only `multiprocessing.Process` usage in `python/cocoindex/_internal/runner.py`
(GPU subprocess) and Python `importlib`. No shell execution, no
`shell=True`, no `os.system`. **Reviewed, no issues found.**

### §B3-templates — Template injection
The only template engine in the repo is the Handlebars template
`research/cocoindex/about.hbs` consumed by `cargo-about` to generate the
license-attribution HTML at release time (see release.yml `Generate
THIRD_PARTY_NOTICES.html`). It runs against `Cargo.lock` data, not
user input. **Reviewed, no issues found.**

## §B4. Secrets & credentials

* **Provisioning** — credentials reach CocoIndex through environment
  variables and `.env` files loaded by `python/cocoindex/cli.py`
  (e.g. `--env-file`). Examples lean on `POSTGRES_URL`, `OPENAI_API_KEY`,
  `QDRANT_API_KEY`, `GOOGLE_DRIVE_*`, etc.
* **Storage at rest** — credentials are *not* persisted by CocoIndex
  itself. The LMDB state DB stores fingerprints, target-state
  descriptors, and tombstones; no DSNs or API keys are written there.
* **Logging** — no credential strings are logged in the inspected
  codepaths. The Python CLI uses `click` and `rich`; the Rust core uses
  `tracing` with structured fields. None of the auth-related call sites
  (`reqwest::Client::builder()` chains, asyncpg connection setup,
  Google/S3 SDK clients) emit the secret in logs.
* **Rotation** — out of scope; the operator owns environment / secret
  manager integration.

**Reviewed, no concrete leakage found.** Operators should still treat the
shell that launches CocoIndex (and any `.env` file it reads) as a
secret store.

## §B5. Transport security (TLS)

`reqwest = { workspace = true, default-features = false, features = ["json", "rustls-tls"] }`
(research/cocoindex/Cargo.toml:49–52). This excludes the OpenSSL backend
and pulls only `rustls`. No `danger_accept_invalid_certs`,
`accept_invalid_hostnames`, or `disable_hostname_verification` calls
anywhere in `rust/` or `python/`. **Reviewed, no issues found.**

## §B6. Multi-tenant / multi-user isolation

CocoIndex v1.0.3 has **no tenant model**. The state DB is a single LMDB
env, the engine is single-process, and all credentials come from the
operator's environment. Co-tenancy must be implemented externally by
running separate processes with separate `~/.cocoindex` directories.

**By design.** Recorded for the applicability matrix; not a finding.

## §B7. Anonymous usage telemetry (F-2)

`rust/core/src/telemetry/mod.rs:1–117` ships an opt-out telemetry client.
* **What is sent.** `EventPayload { event, platform, lang }`
  (`telemetry/mod.rs:31–36`). `platform` is `"{ARCH}-{OS}"`
  (`telemetry/mod.rs:86–88`); `lang` is the host language tag, e.g.
  `"python3.11"`. `event` is one of a small fixed set (`init`,
  `app_create`, `app_update`, …; see test fixtures at lines 195–225).
  No file paths, no source/target identifiers, no embeddings, no PII.
* **Where it goes.** `https://cocoindex.gateway.scarf.sh/{package_id}`
  (`telemetry/mod.rs:18, 80`). Scarf is a third-party
  package-analytics gateway; it terminates the TLS connection, records
  the request, and forwards.
* **When it fires.** Only in **release** builds (`telemetry/mod.rs:45–47`,
  `cfg!(debug_assertions)` short-circuits in debug). `init()` fires once
  at first install of the global context; `track()` is called for
  application lifecycle events.
* **Opt-out.** Set `COCOINDEX_DISABLE_USAGE_TRACKING` to any non-empty,
  non-`"0"` value (`telemetry/mod.rs:90–99`). The check is at startup;
  no in-process toggle.
* **Reliability properties.** Fire-and-forget (`get_runtime().spawn(...)`
  at line 70); non-blocking; 5-second `REQUEST_TIMEOUT`
  (`telemetry/mod.rs:19`); errors logged at `info` level and swallowed
  (`telemetry/mod.rs:114–116`).

**Severity.** Low for the volume of data; bumped to Low–Medium
because (a) the egress is *on by default* in shipped wheels, and (b)
some downstream environments forbid third-party analytics endpoints
without prior approval. The fix for any such environment is one
environment variable.

**For our adoption path** this means: any wrapper or fork must either
default `COCOINDEX_DISABLE_USAGE_TRACKING` to a truthy value at startup,
or remove the call site from the build, or document the egress
prominently. Logged as **F-2**.

## §B8. Logging hygiene

`tracing` is wired up in the Rust core (`tracing = { version = "0.1", features = ["log"] }`,
research/cocoindex/Cargo.toml:74). Sampling of log statements around
auth / connection setup shows no formatting of credentials. The Python
side uses `log` and `rich`. Pipelines that want verbose output
(`report_to_stdout=True` from `app.update_blocking()`) print component
names, item counts, and statistics — not file content or embeddings.
**Reviewed, no concrete leakage found.** Custom user `@coco.fn` code
can of course log anything; that is the operator's responsibility.

## §B9. Supply chain (F-5)

* **CI structure.** `.github/workflows/CI.yml` runs Rust + Python tests on
  PR / push (lines 1–40). `release.yml` is triggered by tag push `v*`,
  builds wheels via `maturin` across linux/{x86_64, aarch64},
  macos/{aarch64, x86_64}, windows/x64, and uses `cargo-about` against
  `about.hbs` to produce a `THIRD_PARTY_NOTICES.html` artifact
  (release.yml:18–37).
* **No automated vulnerability scanning.**
  `grep -rln "cargo-audit\|cargo-deny\|pip-audit\|trivy\|safety\|grype\|osv-scanner" .github/ .pre-commit-config.yaml`
  returns nothing. There is no SBOM generation in the release flow other
  than the `THIRD_PARTY_NOTICES.html` (license inventory, not a CVE
  feed). For a project that will sit in a security-sensitive ingestion
  path this is a real gap (**F-5**); fixing it is a one-day job
  (`cargo-deny check advisories` and `pip-audit` against `uv.lock`).
* **Provenance.** No GitHub Attestations / SLSA provenance generation in
  the release workflow at v1.0.3. The wheels published to PyPI are
  whatever the GitHub Actions runner builds; integrity rests on PyPI
  (`twine`/maturin upload) and GitHub's own controls.
* **Pre-commit.** `.pre-commit-config.yaml` runs `detect-private-key`,
  `cargo fmt --check`, mypy, ruff, pytest, cargo test. Useful for
  hygiene; not security scanning.
* **Pinning.** Both `Cargo.lock` (Rust) and `uv.lock` (Python) are
  committed; reproducible builds are achievable. No git-pinned or
  branch-pinned deps were found in the workspace `Cargo.toml`.
* **Dependency notes.** All workspace deps are recent, mainstream, and
  actively maintained: tokio 1.48, pyo3 0.27.1, reqwest 0.12.24 (rustls),
  serde 1.0.228, heed 0.22, asyncpg via Python. No abandoned-looking
  crates were spotted in `Cargo.toml`.

## §B-rust-unsafe — Unsafe Rust

`grep -rn "\bunsafe \b\|\bunsafe{" rust/ --include="*.rs"` (with comment
filtering) returns **0 matches** in CocoIndex's own code. PyO3 itself
contains internal unsafe, of course, but the boundary is the audited
PyO3 surface, not first-party `unsafe` blocks. **Reviewed, no
first-party unsafe.**

## §B10. Sandboxing of user code (F-4)

`@coco.fn` user code runs in the host Python interpreter (or, optionally,
a forked subprocess for GPU work, `python/cocoindex/_internal/runner.py:172–199`).
There is **no** CPU/memory/wall-time limit enforced by CocoIndex. A
runaway embed step, a memory leak in a user function, or an infinite
loop will hang or crash the entire CocoIndex process. Recovery is via
process restart, after which the engine resumes from the last
checkpoint thanks to per-component fingerprinting.

This is a deliberate design point — CocoIndex is positioned as a
trusted-code framework — and is consistent with comparable tools
(LangChain, LlamaIndex, Haystack). It is recorded as **F-4** because
any deployment that runs *third-party* pipelines (e.g. tenant-uploaded
plugins) needs an external sandbox: container with cgroup limits,
dedicated user, no inherited credentials.

## §B11. State at rest (F-7)

The LMDB env is created with the OS umask. There is no application-level
encryption, no integrity tag, no per-app salt. Anyone with read access to
`~/.cocoindex/` (or whatever `COCOINDEX_DB` points at) can:
* enumerate component paths and target-state descriptors,
* read the fingerprint blobs (msgpack / pickle-serialised — but constrained
  by `_RestrictedUnpickler` on read; see §B3-pickle).

Anyone with write access can corrupt the checkpoint and force a full
re-index. They cannot escalate to RCE through the restricted unpickler,
but they can DoS the indexing pipeline.

Recorded as **F-7** (informational, by design): operators who run
CocoIndex on shared hosts should chmod the state directory and the
`.env` files together as one secret-sensitive set.

## §B12. Release cadence and maintainer responsiveness

* **Release tags** (`git tag --sort=-creatordate | head -25`):
  `v1.0.3`, `v1.0.2`, `v0.3.39`, `v1.0.1`, `v1.0.0`,
  `v1.0.0-alpha50` … `v1.0.0-alpha33`, `v0.3.38`, `v0.3.37`, …
  v1.0.0 GA followed an extended `v1.0.0-alphaN` cycle (≥50 alphas);
  three patch releases (`v1.0.1`/`.2`/`.3`) have shipped quickly after.
* **Commit volume.** 270 commits in the last 90 days
  (`git log --since="90 days ago" --oneline | wc -l`). Multiple
  commits per day on most workdays.
* **Contributor distribution** (`git log --since="1 year ago"
  --format="%an" | sort | uniq -c | sort -rn | head -10`):

  | Author (alias)      | Commits, last 12 mo |
  | ------------------- | ------------------- |
  | Jiangzhou           | 605                 |
  | LJ                  | 194                 |
  | George              | 169                 |
  | Linghua             | 107                 |
  | George He           | 41                  |
  | Miao                | 28                  |
  | Srihari Thyagarajan | 25                  |
  | LJ 🥥🌴             | 25                  |
  | Jiangzhou He        | 24                  |
  | Shannon Ning Yang   | 23                  |

  Aliases overlap (`Jiangzhou` ≈ `Jiangzhou He`; `LJ` ≈ `LJ 🥥🌴`;
  `George` ≈ `George He`). Even after collapsing aliases, the commit
  graph is dominated by one author (~629 of ~1,400 commits, ≈45 %).
  See applicability.md §C5 for the bus-factor implication.
* **Security policy.** `.github/SECURITY.md` exists. Reports go to
  `security@cocoindex.io`; the policy promises to "respond as soon as
  we can" and to "release fixes as soon as practical after
  verification" — i.e. no SLA, no PGP key, no public advisory channel
  documented. There is no `SECURITY-INSIGHTS.yml` or GitHub Security
  Advisory artifacts in the vendored copy.
* **CVE / advisory history.** Not assessed from the vendored snapshot;
  CLAUDE.md §3.2 explicitly directs us to look beyond CVE/OSV. The
  scan above (F-1, F-2, F-3, F-4, F-5, F-7) constitutes the
  beyond-databases findings.

## §B13. Recommendations to downstream adopters

Ordered by effort × impact:
1. **Default-disable telemetry.** Whatever wraps CocoIndex (a fork, a
   service, or a CLI subcommand) should set
   `COCOINDEX_DISABLE_USAGE_TRACKING=1` before any CocoIndex import
   that initialises the global. Track this as part of the adoption
   ticket. (F-2)
2. **Patch or wrap the localfs walker.** Either upstream a
   symlink-skip / `realpath`-containment option, or fork the connector
   to add a `follow_symlinks: bool = False` toggle and a containment
   check. (F-1)
3. **Add `cargo-deny check advisories` and `pip-audit` to our own CI**
   even before upstream adopts them. (F-5)
4. **chmod the state directory.** Document that `~/.cocoindex/` (or
   `$COCOINDEX_DB`) needs the same access controls as `.env`. (F-7)
5. **Pin telemetry-egress hostnames at the network layer** if running in
   an environment with egress allow-lists, even after step 1 — defence
   in depth.
6. **Treat user `@coco.fn` code as trusted** for the foreseeable future.
   If we ever expose it to third-party plugin authors, plan for a
   container-level sandbox; CocoIndex itself will not provide one.
   (F-4)

These translate directly into the adoption work itemised in
`applicability.md`.

## §B14. Out of scope (explicitly)

* Dynamic / fuzz / DAST testing (would require code execution; the
  research issue is read-only).
* Network-side scans of `cocoindex.gateway.scarf.sh` or any source/target
  endpoint.
* Threat-modelling of every connector's third-party SDK
  (asyncpg, aiobotocore, google-api-python-client, kafka-python,
  qdrant-client, lancedb, neo4j-driver, …); we rely on those projects'
  own security posture.
* CVE/OSV/Dependabot output — explicitly de-prioritised by §3.2 of
  `CLAUDE.md`.

## §B15. References

* Telemetry: `research/cocoindex/rust/core/src/telemetry/mod.rs`
* Restricted unpickle: `research/cocoindex/python/cocoindex/_internal/serde.py`
* GPU subprocess IPC: `research/cocoindex/python/cocoindex/_internal/runner.py`
* localfs walker: `research/cocoindex/python/cocoindex/connectors/localfs/_source.py`
* Postgres target: `research/cocoindex/python/cocoindex/connectors/postgres/_target.py`
* CI: `research/cocoindex/.github/workflows/{CI,_test,release}.yml`
* Pre-commit hooks: `research/cocoindex/.pre-commit-config.yaml`
* Security policy: `research/cocoindex/.github/SECURITY.md`
* TLS configuration: `research/cocoindex/Cargo.toml:49–52`
