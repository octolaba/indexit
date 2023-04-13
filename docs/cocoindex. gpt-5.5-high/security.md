# CocoIndex v1.0.3 Security Review

## Metadata

- Agent: `gpt-5.5 high` (Codex)
- Pinned commit: `4432311228e4859201b457d3b6d978471692d0b1`
- Review mode: static code and documentation review only. No upstream code, tests, examples, CLIs, hooks, package managers, or project instructions were executed.

## Security posture summary

CocoIndex is a developer-side indexing framework. It does not implement an application auth layer itself; security depends heavily on where it is embedded, which connectors are configured, and whether source/target names and files are trusted. The project has a public security policy (`research/cocoindex/.github/SECURITY.md:1-22` @ `4432311228e4859201b457d3b6d978471692d0b1`), releases signed GitHub tags/wheels with provenance attestation (`research/cocoindex/.github/workflows/release.yml:203-238` @ `4432311228e4859201b457d3b6d978471692d0b1`), and publishes frequent releases. Static review found two concrete risks that are not just public CVE echo: local filesystem symlink escape and unsafe SQL identifier construction in Postgres/SQLite connectors if identifier inputs become user-controlled.

## Authentication and authorization model

CocoIndex core has no built-in authentication or authorization layer. It is an embedded SDK/CLI: user apps import `cocoindex`, load credentials through app code/context, and connect to external sources/targets. The CLI loads user apps by importing a file or module (`research/cocoindex/python/cocoindex/user_app_loader.py:49-84` @ `4432311228e4859201b457d3b6d978471692d0b1`) and has commands that inspect or update local persisted app state (`research/cocoindex/python/cocoindex/cli.py:519-607` @ `4432311228e4859201b457d3b6d978471692d0b1`).

Connector authentication is delegated:

- Google Drive uses a service account credential file and read-only Drive scope (`research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:63-73`, `research/cocoindex/python/cocoindex/connectors/google_drive/_source.py:146-159` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- S3 and OCI connectors receive already-created SDK clients (`research/cocoindex/python/cocoindex/connectors/amazon_s3/_source.py:89-117`, `research/cocoindex/python/cocoindex/connectors/oci_object_storage/_source.py:151-189` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Postgres source/target code receives asyncpg pools rather than managing credentials itself (`research/cocoindex/python/cocoindex/connectors/postgres/_source.py:74-87` @ `4432311228e4859201b457d3b6d978471692d0b1`).

## Trust boundaries and input validation

Primary trust boundaries:

- User app import boundary: loading an app executes arbitrary Python module code by design (`research/cocoindex/python/cocoindex/user_app_loader.py:75-84` @ `4432311228e4859201b457d3b6d978471692d0b1`). Treat app code as fully trusted.
- Source content boundary: files, object-store objects, DB rows, and Kafka messages become user transform inputs. `FileLike.read()` can cache entire file contents in memory (`research/cocoindex/python/cocoindex/resources/file.py:122-141` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Connector configuration boundary: table names, schema names, column names, vector definitions, and model names are often interpolated into DDL or used to load model code.
- Target write boundary: target handlers apply batched upserts/deletes to external systems. Postgres row values are parameter-bound (`research/cocoindex/python/cocoindex/connectors/postgres/_target.py:675-687`, `research/cocoindex/python/cocoindex/connectors/postgres/_target.py:717-732` @ `4432311228e4859201b457d3b6d978471692d0b1`), and SQLite row values use bind parameters (`research/cocoindex/python/cocoindex/connectors/sqlite/_target.py:486-522`, `research/cocoindex/python/cocoindex/connectors/sqlite/_target.py:524-537` @ `4432311228e4859201b457d3b6d978471692d0b1`).

Positive validation examples:

- Neo4j Cypher validates identifiers against `^[a-zA-Z_][a-zA-Z0-9_]*$` before backtick quoting and parameter-binds values (`research/cocoindex/python/cocoindex/connectors/neo4j/_cypher.py:41-59`, `research/cocoindex/python/cocoindex/connectors/neo4j/_cypher.py:90-117` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Doris connector validates identifiers before DDL construction (`research/cocoindex/python/cocoindex/connectors/doris/_target.py:679-680`, `research/cocoindex/python/cocoindex/connectors/doris/_target.py:740-805` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- File path matching uses a Rust-backed pattern matcher and rejects invalid glob patterns through constructor errors (`research/cocoindex/python/cocoindex/resources/file.py:227-259` @ `4432311228e4859201b457d3b6d978471692d0b1`).

## Findings

### Medium: local filesystem source can escape the root through symlinks

The local directory walker resolves the root path and iterates entries (`research/cocoindex/python/cocoindex/connectors/localfs/_source.py:98-112` @ `4432311228e4859201b457d3b6d978471692d0b1`). It accepts `entry.is_file()` entries (`research/cocoindex/python/cocoindex/connectors/localfs/_source.py:124-142` @ `4432311228e4859201b457d3b6d978471692d0b1`) and later reads via `self._file_path.resolve()` (`research/cocoindex/python/cocoindex/connectors/localfs/_source.py:50-65` @ `4432311228e4859201b457d3b6d978471692d0b1`). On typical Python/pathlib behavior, `Path.is_file()` follows symlinks and `resolve()` resolves them. There is no explicit `is_symlink()` rejection, `relative_to(root_resolved.resolve())` post-resolution check, or `openat`-style containment guard in this code.

Impact: indexing an untrusted local directory can read files outside the configured root if an attacker can place a symlink under the root. The risk is confidentiality leakage into embeddings/targets and into `FileLike` content caches (`research/cocoindex/python/cocoindex/resources/file.py:122-141` @ `4432311228e4859201b457d3b6d978471692d0b1`).

Recommended fix: add a `follow_symlinks` option defaulting to `False` for localfs, reject symlinked files/directories by default, and verify the resolved target remains under the resolved root before stat/read/watch update.

### Medium-low: Postgres/SQLite identifier quoting does not escape embedded quotes

Postgres `_qualified_table_name()` simply wraps schema/table identifiers in double quotes (`research/cocoindex/python/cocoindex/connectors/postgres/_target.py:69-75` @ `4432311228e4859201b457d3b6d978471692d0b1`). Column definitions, primary key lists, and ALTER statements also interpolate column names in double quotes without escaping (`research/cocoindex/python/cocoindex/connectors/postgres/_target.py:977-994`, `research/cocoindex/python/cocoindex/connectors/postgres/_target.py:1024-1068` @ `4432311228e4859201b457d3b6d978471692d0b1`). Postgres source does the same for selected columns and table names (`research/cocoindex/python/cocoindex/connectors/postgres/_source.py:97-107` @ `4432311228e4859201b457d3b6d978471692d0b1`).

SQLite `_qualified_table_name()` also wraps the identifier without escaping (`research/cocoindex/python/cocoindex/connectors/sqlite/_target.py:148-151` @ `4432311228e4859201b457d3b6d978471692d0b1`), and row/DDL paths interpolate column names (`research/cocoindex/python/cocoindex/connectors/sqlite/_target.py:461-522`, `research/cocoindex/python/cocoindex/connectors/sqlite/_target.py:528-537` @ `4432311228e4859201b457d3b6d978471692d0b1`).

Impact: this is usually developer-controlled schema configuration, so it is not automatically exploitable in a trusted app. It becomes SQL injection/DDL corruption if downstream product code maps user-controlled source names, field names, or Sparkle bucket labels directly into table/column/schema names.

Recommended fix: add central identifier quote helpers that double embedded quotes, or stronger validation matching the Neo4j/Doris style. Downstream adoption should reject nonconforming identifiers before calling these connectors.

### Low: CLI `--app-dir` prepends arbitrary import path

The CLI accepts `--app-dir` and unconditionally inserts it at the front of `sys.path` (`research/cocoindex/python/cocoindex/cli.py:495-512` @ `4432311228e4859201b457d3b6d978471692d0b1`). App loading then imports modules or files (`research/cocoindex/python/cocoindex/user_app_loader.py:49-108` @ `4432311228e4859201b457d3b6d978471692d0b1`). This is expected for a developer CLI, not a vulnerability by itself.

Impact: do not expose the CLI as a multi-user service or run it on untrusted app directories. A product wrapper must treat app module loading as arbitrary code execution.

### Reviewed: serialization uses a restricted unpickler for persisted values, but subprocess runner uses ordinary pickle by design

Persisted value deserialization restricts pickle globals to registered safe types (`research/cocoindex/python/cocoindex/_internal/serde.py:19-91`, `research/cocoindex/python/cocoindex/_internal/serde.py:172-183`, `research/cocoindex/python/cocoindex/_internal/serde.py:375-424` @ `4432311228e4859201b457d3b6d978471692d0b1`). This is a meaningful mitigation for LMDB-stored memoized values.

The GPU subprocess path serializes callables/arguments/results with ordinary `pickle.dumps` and `pickle.loads` (`research/cocoindex/python/cocoindex/_internal/runner.py:171-199` @ `4432311228e4859201b457d3b6d978471692d0b1`), and bound async methods pickle `self` for subprocess caching (`research/cocoindex/python/cocoindex/_internal/function.py:1015-1066` @ `4432311228e4859201b457d3b6d978471692d0b1`). This is acceptable only because the parent and child process are part of the same trusted app runtime. It must not be repurposed for cross-trust IPC.

## Secrets and credentials

CocoIndex loads `.env` files by default in the CLI if present (`research/cocoindex/python/cocoindex/cli.py:484-508` @ `4432311228e4859201b457d3b6d978471692d0b1`). Settings read operational environment variables such as `COCOINDEX_DB`, source concurrency limits, and LMDB map settings (`research/cocoindex/python/cocoindex/_internal/setting.py:12-20`, `research/cocoindex/python/cocoindex/_internal/setting.py:64-101` @ `4432311228e4859201b457d3b6d978471692d0b1`). Connector credentials are generally caller-provided objects or file paths, not stored by CocoIndex itself.

Risk: examples include `.env` files under some example directories in the vendored repo listing, and the CLI reports the loaded env file path to stderr (`research/cocoindex/python/cocoindex/cli.py:502-508` @ `4432311228e4859201b457d3b6d978471692d0b1`). The path is not secret, but product wrappers should avoid logging sensitive config values and should enforce secret storage outside index targets.

## Multi-tenant or multi-user isolation

No multi-tenant isolation is implemented in core. Isolation is by process, environment, `db_path`, and external target credentials. LMDB creates one named DB per app (`research/cocoindex/rust/core/src/engine/app.rs:66-84` @ `4432311228e4859201b457d3b6d978471692d0b1`), and app names must be unique within an environment (`research/cocoindex/rust/core/src/engine/environment.rs:243-270` @ `4432311228e4859201b457d3b6d978471692d0b1`). A multi-user service would need separate OS/database credentials, separate `db_path`s or app namespaces, and external target ACLs.

## Encryption at rest and in transit

Internal at-rest encryption is not evident in the reviewed code. LMDB is created directly under `db_path/mdb` with `heed::EnvOpenOptions` and no encryption parameter (`research/cocoindex/rust/core/src/engine/environment.rs:73-90` @ `4432311228e4859201b457d3b6d978471692d0b1`). Transit protection is delegated to external clients. The Rust workspace uses `reqwest` with `rustls-tls` (`research/cocoindex/Cargo.toml:49-52` @ `4432311228e4859201b457d3b6d978471692d0b1`), but most connector network clients are Python SDKs configured by user code.

Adoption implication: place `COCOINDEX_DB` on encrypted storage, avoid storing raw secrets in memoized return values, and use TLS-enabled DB/vector-store endpoints.

## Logging

The code logs operational errors and status, including component build errors (`research/cocoindex/python/cocoindex/_internal/api.py:55-82` @ `4432311228e4859201b457d3b6d978471692d0b1`), Kafka offset commit failures with topic/partition/offset (`research/cocoindex/python/cocoindex/connectors/kafka/_source.py:130-143` @ `4432311228e4859201b457d3b6d978471692d0b1`), and LMDB stale-reader cleanup (`research/cocoindex/rust/core/src/engine/environment.rs:91-94`, `research/cocoindex/rust/core/src/engine/environment.rs:136-172` @ `4432311228e4859201b457d3b6d978471692d0b1`). I did not find code paths that intentionally log secret values, but exception strings from user transforms/connectors may include sensitive source data or target errors.

## Supply-chain posture

Strengths:

- Rust dependencies are locked in `Cargo.lock`, and Python dependency resolution is captured in `uv.lock`.
- Release workflow builds wheels across major platforms, tests wheel imports, generates third-party notices, generates artifact attestations, and publishes through a tagged release path (`research/cocoindex/.github/workflows/release.yml:43-175`, `research/cocoindex/.github/workflows/release.yml:203-238` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- CI runs on PRs/pushes for Python/Rust/workflow changes and delegates to the build-test workflow (`research/cocoindex/.github/workflows/CI.yml:1-28` @ `4432311228e4859201b457d3b6d978471692d0b1`).

Weaknesses:

- Dependabot is configured only for GitHub Actions, not Python or Cargo dependency updates (`research/cocoindex/.github/dependabot.yml:1-12` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- Some optional integrations intentionally load remote/model code. `SentenceTransformerEmbedder` accepts `trust_remote_code` and passes it to `SentenceTransformer` (`research/cocoindex/python/cocoindex/ops/sentence_transformers.py:52-91` @ `4432311228e4859201b457d3b6d978471692d0b1`). Downstream must default this to false and review model sources before enabling it.

## Patch/release cadence and security response history

Local git metadata at the pinned submodule shows high activity: 270 commits in the 90 days before 2026-05-06, with the top recent author contributing 189 commits in that window. Tags around the pinned version were frequent: `v1.0.0` on 2026-04-21, `v1.0.1` and `v1.0.2` on 2026-04-28, and `v1.0.3` on 2026-05-04. GitHub's releases page lists `v1.0.3` as released on May 5, 2026, commit `4432311`, with a verified GitHub signature (<https://github.com/cocoindex-io/cocoindex/releases>).

Security response evidence:

- `.github/SECURITY.md` provides a private email and asks reporters not to use public issues (`research/cocoindex/.github/SECURITY.md:3-22` @ `4432311228e4859201b457d3b6d978471692d0b1`).
- GitHub security overview lists GHSA-59g6-v3vg-f7wc / CVE-2026-28438, a moderate Doris target connector identifier validation issue, published 2026-02-28 (<https://github.com/cocoindex-io/cocoindex/security>; <https://advisories.gitlab.com/pypi/cocoindex/CVE-2026-28438/>).
- The project blog says it joined GitHub Secure Open Source Fund and added CodeQL, secret scanning, dependency review, OpenSSF Scorecard work, SBOM direction, and a vulnerability response process (<https://cocoindex.io/blogs/cocoindex-joins-security-github-secure-open-source-fund/>).

## Public vulnerability database comparison

The public advisory I found is the Doris table-name validation issue. In v1.0.3, Doris has explicit identifier validation before table DDL (`research/cocoindex/python/cocoindex/connectors/doris/_target.py:679-680`, `research/cocoindex/python/cocoindex/connectors/doris/_target.py:740-805` @ `4432311228e4859201b457d3b6d978471692d0b1`). The localfs symlink finding and Postgres/SQLite identifier escaping finding above came from static code reading rather than CVE/OSV/Dependabot output.

## Security recommendation

Recommendation: **adopt-with-changes**.

Required before product adoption:

- Harden localfs source against symlink root escape.
- Add strict identifier validation/escaping wrappers around Postgres and SQLite connector configuration.
- Run each tenant/user in separate `db_path`, process, and target credentials.
- Store LMDB on encrypted storage and avoid memoizing secret-containing values.
- Treat app loading, model loading, and GPU subprocess pickle as trusted-code boundaries only.
