# QMD v2.1.0 Security Review

## Metadata

- Agent slug: `gpt-5.5-xhigh`
- Subject: `tobi/qmd`
- Pinned tag: `v2.1.0`
- Pinned commit: `65cd1b3fd02891d1ee0eefa751620918664fa321`
- Scope: static review only. No upstream code, tests, package managers, scripts, CLIs, examples, or services were executed.

All qmd-specific citations refer to `research/qmd/` at commit `65cd1b3fd02891d1ee0eefa751620918664fa321`.

## Security Posture Summary

QMD is designed as a local, personal indexing tool. That design avoids many remote-service concerns, but it also means core controls that a downstream multi-source product would need are absent: no authentication or authorization layer, no tenant/user separation, no at-rest encryption, no permission propagation from sources, and no conflict-aware sync boundary. The main security-sensitive surfaces are local filesystem indexing, YAML config, optional shell update hooks, SQLite persistence, local model download/loading, MCP stdio/HTTP access, and agent-facing instructions.

Positive findings: QMD uses prepared SQL parameters for most user-controlled values, sanitizes FTS terms before `MATCH`, disables symlink directory following in glob scans, pins npm dependency versions exactly, publishes npm artifacts with provenance, and binds the HTTP server to localhost (`research/qmd/src/store.ts:2777`, `research/qmd/src/store.ts:2927`, `research/qmd/src/store.ts:2936`, `research/qmd/src/store.ts:1189`, `research/qmd/package.json:47`, `research/qmd/.github/workflows/publish.yml:38`, `research/qmd/.github/workflows/publish.yml:39`, `research/qmd/src/mcp/server.ts:797` @ `65cd1b3...`).

Residual risk: these positives do not make QMD safe as-is for a product that indexes heterogeneous user data, because QMD's trust model is "local user controls the machine and config" rather than "server protects users, sources, permissions, and tenants from each other."

## Trust Boundaries

| Boundary | Inputs | Handling | Risk |
| --- | --- | --- | --- |
| Filesystem collection boundary | Collection `path`, `pattern`, `ignore`, file content | `fastGlob` scans with `followSymbolicLinks: false`; files are read as UTF-8 and inserted into SQLite (`research/qmd/src/store.ts:1189`, `research/qmd/src/store.ts:1211` @ `65cd1b3...`). | No source permission model; possible symlink/file containment ambiguity after `realpathSync`. |
| YAML/SDK config boundary | Collection metadata, context, update commands, model URIs | YAML is parsed without schema validation in `loadConfig`; config is mirrored into SQLite (`research/qmd/src/collections.ts:162`, `research/qmd/src/store.ts:1005` @ `65cd1b3...`). | Config is trusted; `update` can execute shell; context can influence MCP instructions. |
| CLI boundary | User command-line query/path/glob options | Query parsing validates typed query syntax; FTS terms are sanitized (`research/qmd/src/cli/qmd.ts:2130`, `research/qmd/src/store.ts:2777` @ `65cd1b3...`). | CLI user is assumed trusted; output can contain sensitive indexed content. |
| MCP/HTTP boundary | JSON-RPC, `/query`, `/search`, `/mcp`, `/health` | HTTP handler parses JSON and routes requests; server binds localhost (`research/qmd/src/mcp/server.ts:637`, `research/qmd/src/mcp/server.ts:650`, `research/qmd/src/mcp/server.ts:703`, `research/qmd/src/mcp/server.ts:797` @ `65cd1b3...`). | No authentication, authorization, body-size limit, or rate limiting in QMD's handler. |
| Model supply chain boundary | Hugging Face model URI and remote file | Defaults point to `hf:` URIs; `pullModels` checks remote ETags and caches model files (`research/qmd/src/llm.ts:193`, `research/qmd/src/llm.ts:239`, `research/qmd/src/llm.ts:251` @ `65cd1b3...`). | No immutable revision or checksum validation in QMD code. |
| Agent prompt boundary | Global context, collection context, returned documents | MCP instructions include global/collection context; resources/tools return document content (`research/qmd/src/mcp/server.ts:101`, `research/qmd/src/mcp/server.ts:113`, `research/qmd/src/mcp/server.ts:120`, `research/qmd/src/mcp/server.ts:206` @ `65cd1b3...`). | User-controlled context or document text can steer downstream agents. |

## Findings

### S1. Unauthenticated localhost HTTP/MCP API exposes indexed content to any local client

Severity: **High for product embedding; medium for QMD's single-user local threat model**.

The HTTP server registers `/query`/`/search`, `/mcp`, and `/health` routes and binds to `localhost`, but the handler does not require a token, client identity, origin check, or authorization decision before executing searches or returning document snippets (`research/qmd/src/mcp/server.ts:637`, `research/qmd/src/mcp/server.ts:650`, `research/qmd/src/mcp/server.ts:672`, `research/qmd/src/mcp/server.ts:697`, `research/qmd/src/mcp/server.ts:703`, `research/qmd/src/mcp/server.ts:797` @ `65cd1b3...`). The MCP session ID is a transport session mechanism, not an access-control boundary, because unauthenticated initialize requests can create a session (`research/qmd/src/mcp/server.ts:713`, `research/qmd/src/mcp/server.ts:729` @ `65cd1b3...`).

Impact: any local process able to connect to localhost can query the index and retrieve snippets or documents through MCP tools. A downstream product cannot expose this server on a workstation or shared host without adding authentication, authorization, rate limiting, body-size limits, and auditing.

Recommended downstream action: wrap or fork the HTTP server to require a local auth token or OS-bound credential, enforce per-source permissions before search and retrieval, and disable unauthenticated REST aliases.

### S2. Collection `update` commands execute arbitrary shell from trusted YAML

Severity: **High when config is imported, synced, or edited by untrusted parties**.

The collection model includes an optional `update?: string` field described as an optional bash command (`research/qmd/src/collections.ts:27`, `research/qmd/src/collections.ts:32` @ `65cd1b3...`). During `qmd update`, the CLI reads that field and runs `bash -c <update>` with the collection directory as `cwd`, then prints stdout/stderr and exits on nonzero status (`research/qmd/src/cli/qmd.ts:554`, `research/qmd/src/cli/qmd.ts:559`, `research/qmd/src/cli/qmd.ts:573`, `research/qmd/src/cli/qmd.ts:580` @ `65cd1b3...`). The README/CLI tips even suggest an update command containing git operations (`research/qmd/src/cli/qmd.ts:509`, `research/qmd/src/cli/qmd.ts:518` @ `65cd1b3...`).

Impact: this is intentional automation for a local trusted user, but it becomes command execution if a shared qmd config, repo-local config, or product-generated collection definition is attacker-controlled. The command output can also leak secrets to terminal logs.

Recommended downstream action: do not carry this surface into product code. Replace shell strings with audited connector-specific sync jobs, or require explicit per-run confirmation and allowlists.

### S3. Hugging Face model downloads are not pinned to immutable revisions or verified checksums

Severity: **Medium**.

Default models are specified as Hugging Face `hf:` URIs without commit/revision digests (`research/qmd/src/llm.ts:193`, `research/qmd/src/llm.ts:196`, `research/qmd/src/llm.ts:197`, `research/qmd/src/llm.ts:199` @ `65cd1b3...`). `getRemoteEtag` checks `https://huggingface.co/{repo}/resolve/main/{file}` and `pullModels` compares/writes ETags, but the QMD code does not pin immutable model revisions or validate a known digest (`research/qmd/src/llm.ts:239`, `research/qmd/src/llm.ts:272`, `research/qmd/src/llm.ts:295`, `research/qmd/src/llm.ts:297` @ `65cd1b3...`). `resolveModelFile` is then used to download or resolve the model path (`research/qmd/src/llm.ts:592`, `research/qmd/src/llm.ts:595` @ `65cd1b3...`).

Impact: model content can change upstream while retaining the same configured URI. For a product that depends on stable retrieval semantics or model provenance, this is not auditable enough.

Recommended downstream action: pin model revisions and expected SHA-256 digests, record model provenance in index metadata, and require explicit migration/re-embedding when model IDs change.

### S4. User-configurable context is injected into MCP server instructions

Severity: **Medium**.

The MCP server builds initialize instructions from index state. It includes global context and collection context text directly in the instruction string (`research/qmd/src/mcp/server.ts:101`, `research/qmd/src/mcp/server.ts:106`, `research/qmd/src/mcp/server.ts:113`, `research/qmd/src/mcp/server.ts:120`, `research/qmd/src/mcp/server.ts:123` @ `65cd1b3...`). Context can be set through collection config, SDK methods, and store context updates (`research/qmd/src/collections.ts:31`, `research/qmd/src/index.ts:457`, `research/qmd/src/store.ts:973` @ `65cd1b3...`). Returned resources also prepend context as an HTML comment before document text (`research/qmd/src/mcp/server.ts:206`, `research/qmd/src/mcp/server.ts:207` @ `65cd1b3...`).

Impact: if context text is copied from untrusted sources, another user, or an indexed repository, it can become instruction-like content delivered to an agent at a privileged layer. This is a prompt-injection risk in agentic integrations.

Recommended downstream action: treat context as untrusted data, escape/label it as data, keep system/tool instructions static, and add policy that indexed content/context must not override agent/developer instructions.

### S5. SQLite index stores full document bodies and LLM cache in plaintext

Severity: **Medium**.

The default DB path resolves under the user's cache directory (`research/qmd/src/store.ts:530`, `research/qmd/src/store.ts:544` @ `65cd1b3...`). The schema stores full document text in `content.doc`, document metadata in `documents`, and LLM results in `llm_cache.result` (`research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:776` @ `65cd1b3...`). There is no encryption setup in `initializeDatabase`; it loads sqlite-vec, enables WAL and foreign keys, then creates tables (`research/qmd/src/store.ts:729`, `research/qmd/src/store.ts:739` @ `65cd1b3...`).

Impact: any process or user with filesystem access to the SQLite file can read indexed documents, metadata, and cached query/rerank outputs. In WAL mode, sensitive data may also reside in WAL/shm side files until checkpointed.

Recommended downstream action: use an encrypted store or OS keychain-backed per-user encryption, define retention policy for caches, and avoid writing data that source permissions do not allow the current principal to persist.

### S6. File containment relies on glob behavior; no post-realpath collection-boundary check

Severity: **Medium-low**.

Reindexing runs `fastGlob` with `followSymbolicLinks: false`, which reduces symlink traversal, but then resolves each matching file with `getRealPath(resolve(collectionPath, relativeFile))` and reads that resolved path without checking that the resolved target remains inside the collection root (`research/qmd/src/store.ts:1189`, `research/qmd/src/store.ts:1192`, `research/qmd/src/store.ts:1206`, `research/qmd/src/store.ts:1207`, `research/qmd/src/store.ts:1211` @ `65cd1b3...`). The CLI indexing path duplicates the same pattern (`research/qmd/src/cli/qmd.ts:1521`, `research/qmd/src/cli/qmd.ts:1524`, `research/qmd/src/cli/qmd.ts:1546`, `research/qmd/src/cli/qmd.ts:1547`, `research/qmd/src/cli/qmd.ts:1551` @ `65cd1b3...`).

Impact: if symlinked files are reported by the glob library in a platform-specific case, QMD could index the symlink target under a virtual path inside the collection. Even when not exploitable with current `fast-glob` behavior, there is no explicit containment invariant in QMD's code.

Recommended downstream action: after realpath resolution, verify `realFile.startsWith(realCollectionRoot + pathSeparator)` or avoid dereferencing symlinked files entirely.

### S7. Query and update logging can disclose sensitive terms, paths, and command output

Severity: **Low-medium**.

The HTTP server creates request labels from tool names and arguments, including query/path/pattern text, and logs them on each request (`research/qmd/src/mcp/server.ts:608`, `research/qmd/src/mcp/server.ts:615`, `research/qmd/src/mcp/server.ts:619`, `research/qmd/src/mcp/server.ts:620`, `research/qmd/src/mcp/server.ts:746` @ `65cd1b3...`). The update command runner prints stdout and stderr from configured shell commands (`research/qmd/src/cli/qmd.ts:573`, `research/qmd/src/cli/qmd.ts:576` @ `65cd1b3...`). Daemon mode truncates and writes logs to `mcp.log` under the qmd cache directory (`research/qmd/src/cli/qmd.ts:3207`, `research/qmd/src/cli/qmd.ts:3212` @ `65cd1b3...`).

Impact: private search terms, file paths, and command output can land in terminal logs or daemon logs. This matters if the indexed corpus includes sensitive local notes or work documents.

Recommended downstream action: redact query strings by default, log structured event IDs rather than raw content, and gate verbose logging behind explicit debug mode.

## Reviewed Categories With No Concrete Issue Found

- **FTS SQL injection:** reviewed `buildFTS5Query` and `searchFTS`. FTS terms are reduced to letters/numbers/apostrophes/underscores, phrase terms are reconstructed, and the resulting FTS expression is passed as a prepared parameter (`research/qmd/src/store.ts:2777`, `research/qmd/src/store.ts:2846`, `research/qmd/src/store.ts:2927`, `research/qmd/src/store.ts:2936` @ `65cd1b3...`). No direct SQL string interpolation of raw query text was found in this path.
- **Collection filter SQL injection:** collection names are bound through prepared parameters in FTS search and collection lookup paths (`research/qmd/src/store.ts:2964`, `research/qmd/src/store.ts:2966`, `research/qmd/src/store.ts:902` @ `65cd1b3...`). No direct SQL interpolation of raw collection names was found in those paths.
- **XML/CSV output escaping:** XML output escapes XML special characters, and CSV output quotes comma/quote/newline values (`research/qmd/src/cli/formatter.ts:72`, `research/qmd/src/cli/formatter.ts:81`, `research/qmd/src/cli/formatter.ts:196`, `research/qmd/src/cli/formatter.ts:292` @ `65cd1b3...`). Markdown output intentionally emits document bodies in fences and is not a sanitization boundary (`research/qmd/src/cli/formatter.ts:275`, `research/qmd/src/cli/formatter.ts:283` @ `65cd1b3...`).
- **Runaway embedding/rerank memory:** reviewed v2.1.0 changes around context sizing, batching, error aborts, and truncation. Embedding validates positive batch limits, caps error continuation, truncates oversized text in the LLM adapter, and rerank truncates documents by model token budget (`research/qmd/src/store.ts:1317`, `research/qmd/src/store.ts:1501`, `research/qmd/src/llm.ts:875`, `research/qmd/src/llm.ts:1160` @ `65cd1b3...`). This is not a security guarantee, but static review did not find unbounded "embed entire corpus in one call" behavior in the current pipeline.

## Authentication And Authorization

QMD has no application-level authentication or authorization model. CLI access relies on the OS user. MCP stdio is started by the client process (`research/qmd/src/mcp/server.ts:540` @ `65cd1b3...`). HTTP binds to localhost, but request handling does not check a credential before `/query`, `/search`, or `/mcp` operations (`research/qmd/src/mcp/server.ts:637`, `research/qmd/src/mcp/server.ts:650`, `research/qmd/src/mcp/server.ts:703`, `research/qmd/src/mcp/server.ts:797` @ `65cd1b3...`). There is no per-document permission check in retrieval; `getDocumentBody` returns body text for matched active documents (`research/qmd/src/store.ts:3492`, `research/qmd/src/store.ts:3504` @ `65cd1b3...`).

## Secrets And Credentials

Runtime QMD does not define a secrets vault. Model configuration is via environment variables or YAML model config (`research/qmd/src/llm.ts:438`, `research/qmd/src/collections.ts:37` @ `65cd1b3...`). CI publish uses `NPM_TOKEN` and GitHub's token in GitHub Actions (`research/qmd/.github/workflows/publish.yml:39`, `research/qmd/.github/workflows/publish.yml:41`, `research/qmd/.github/workflows/publish.yml:51`, `research/qmd/.github/workflows/publish.yml:57` @ `65cd1b3...`). The product does not expose credential storage or rotation primitives in the pinned code. Any secrets printed by update hooks or indexed files would be treated as ordinary text.

## Multi-Tenant Or Multi-User Isolation

There is no multi-tenant model. The schema stores documents by collection and path, not by user, tenant, source account, ACL, or principal (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:805` @ `65cd1b3...`). The SDK `createStore` accepts one database path and returns a store over that path (`research/qmd/src/index.ts:338`, `research/qmd/src/index.ts:346` @ `65cd1b3...`). The HTTP server shares one store across all sessions (`research/qmd/src/mcp/server.ts:567`, `research/qmd/src/mcp/server.ts:575` @ `65cd1b3...`). Downstream multi-user use would need a separate isolation layer.

## Encryption At Rest And In Transit

At rest: no SQLite encryption is configured. The database is opened directly with `better-sqlite3` or Bun SQLite, and `initializeDatabase` sets WAL and foreign keys only (`research/qmd/src/db.ts:61`, `research/qmd/src/store.ts:729`, `research/qmd/src/store.ts:739` @ `65cd1b3...`). Document content and LLM cache are plaintext table values (`research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:776` @ `65cd1b3...`).

In transit: stdio MCP has no network transport. HTTP MCP is bound to localhost over plain HTTP (`research/qmd/src/mcp/server.ts:565`, `research/qmd/src/mcp/server.ts:797` @ `65cd1b3...`). Model metadata/download checks use HTTPS Hugging Face URLs (`research/qmd/src/llm.ts:239` @ `65cd1b3...`).

## Supply Chain

The direct package dependencies are exact versions, not semver ranges (`research/qmd/package.json:47` @ `65cd1b3...`). The lockfiles contain integrity entries for key packages and native optional dependencies, including `@modelcontextprotocol/sdk`, `better-sqlite3`, `node-llama-cpp`, `sqlite-vec`, and `web-tree-sitter` (`research/qmd/pnpm-lock.yaml:261`, `research/qmd/pnpm-lock.yaml:654`, `research/qmd/pnpm-lock.yaml:271`, `research/qmd/pnpm-lock.yaml:306`, `research/qmd/pnpm-lock.yaml:637`, `research/qmd/pnpm-lock.yaml:728` @ `65cd1b3...`). Release workflow publishes with npm provenance (`research/qmd/.github/workflows/publish.yml:38`, `research/qmd/.github/workflows/publish.yml:39` @ `65cd1b3...`).

Gaps: GitHub Actions use floating action tags such as `actions/checkout@v4`, `actions/setup-node@v4`, `oven-sh/setup-bun@v2`, and `cachix/install-nix-action@v31`, not commit SHAs (`research/qmd/.github/workflows/ci.yml:20`, `research/qmd/.github/workflows/ci.yml:22`, `research/qmd/.github/workflows/ci.yml:52`, `research/qmd/.github/workflows/nix.yml:21` @ `65cd1b3...`). CI's Node path uses `npm install`, not `npm ci`, and there is no `package-lock.json` in the pinned root, while Bun paths use `--frozen-lockfile` (`research/qmd/.github/workflows/ci.yml:34`, `research/qmd/.github/workflows/ci.yml:64`, `research/qmd/.github/workflows/publish.yml:25` @ `65cd1b3...`). The package `prepare` script installs git hooks in a git checkout (`research/qmd/package.json:23`, `research/qmd/package.json:24`, `research/qmd/scripts/install-hooks.sh:4`, `research/qmd/scripts/install-hooks.sh:16` @ `65cd1b3...`).

## Patch And Release Cadence

The local changelog shows rapid releases: v1.0.0 on 2026-02-15, v1.1.x releases in February/March 2026, v2.0.0 and v2.0.1 on 2026-03-10, and v2.1.0 on 2026-04-05 (`research/qmd/CHANGELOG.md:5`, `research/qmd/CHANGELOG.md:101`, `research/qmd/CHANGELOG.md:115`, `research/qmd/CHANGELOG.md:140`, `research/qmd/CHANGELOG.md:247` @ `65cd1b3...`). The v2.1.0 entry says 25+ community PRs fixed embedding stability, BM25 accuracy, and cross-platform launcher issues (`research/qmd/CHANGELOG.md:7`, `research/qmd/CHANGELOG.md:10` @ `65cd1b3...`). The pinned tree has publish automation with tests before npm publish and GitHub release creation (`research/qmd/.github/workflows/publish.yml:25`, `research/qmd/.github/workflows/publish.yml:28`, `research/qmd/.github/workflows/publish.yml:38`, `research/qmd/.github/workflows/publish.yml:51` @ `65cd1b3...`).

Security response history is unclear from the pinned repository. Static file inspection found no `SECURITY.md` file under `research/qmd/`, and the changelog entries reviewed are mostly feature and bug-fix oriented rather than security-advisory oriented. This should be treated as unknown, not negative proof.

## Own-Scan Risks Beyond Public Databases

The following are source-review findings rather than public CVE/OSV/Dependabot echoes:

- Unauthenticated localhost MCP/REST access to indexed content (`research/qmd/src/mcp/server.ts:637` @ `65cd1b3...`).
- Arbitrary shell execution through trusted collection `update` config (`research/qmd/src/cli/qmd.ts:554` @ `65cd1b3...`).
- Mutable model supply chain via unpinned Hugging Face `main` model URLs (`research/qmd/src/llm.ts:239` @ `65cd1b3...`).
- Prompt-injection exposure through context injected into MCP instructions (`research/qmd/src/mcp/server.ts:101` @ `65cd1b3...`).
- Plaintext persistence of full indexed content and LLM cache (`research/qmd/src/store.ts:746`, `research/qmd/src/store.ts:776` @ `65cd1b3...`).
- Missing explicit realpath containment check after filesystem globbing (`research/qmd/src/store.ts:1207` @ `65cd1b3...`).

## Security Checklist

| Question | Answer |
| --- | --- |
| Authentication and authorization model? | None in QMD; OS user and localhost binding are the effective boundary (`research/qmd/src/mcp/server.ts:565`, `research/qmd/src/mcp/server.ts:797` @ `65cd1b3...`). |
| Trust boundaries and input validation? | Boundaries are filesystem/config/CLI/MCP/model downloads. CLI structured queries validate line syntax, FTS terms are sanitized, but HTTP JSON lacks zod validation/body limits in the REST path (`research/qmd/src/cli/qmd.ts:2130`, `research/qmd/src/store.ts:2777`, `research/qmd/src/mcp/server.ts:650` @ `65cd1b3...`). |
| Secrets provisioning/storage/rotation? | No runtime secrets manager. Publish secrets exist only in GitHub Actions; product credentials are not modeled (`research/qmd/.github/workflows/publish.yml:39`, `research/qmd/.github/workflows/publish.yml:41` @ `65cd1b3...`). |
| Multi-tenant isolation? | Not applicable to QMD's design; schema has collection/path but no tenant/user/ACL columns (`research/qmd/src/store.ts:758`, `research/qmd/src/store.ts:805` @ `65cd1b3...`). |
| Encryption at rest/in transit? | No at-rest encryption; localhost HTTP is plaintext; Hugging Face model access uses HTTPS (`research/qmd/src/db.ts:61`, `research/qmd/src/store.ts:746`, `research/qmd/src/mcp/server.ts:797`, `research/qmd/src/llm.ts:239` @ `65cd1b3...`). |
| Logging sensitive content? | HTTP logs query/path/pattern labels; update hooks print stdout/stderr; daemon logs are file-backed (`research/qmd/src/mcp/server.ts:608`, `research/qmd/src/mcp/server.ts:746`, `research/qmd/src/cli/qmd.ts:573`, `research/qmd/src/cli/qmd.ts:3207` @ `65cd1b3...`). |
| Patch/release cadence and response history? | Active release cadence in changelog and CI/publish automation; security response process is unknown because no `SECURITY.md` was present in the pinned tree (`research/qmd/CHANGELOG.md:5`, `research/qmd/CHANGELOG.md:10`, `research/qmd/.github/workflows/publish.yml:38` @ `65cd1b3...`). |
| Concrete own-scan risks not in public CVE/OSV/Dependabot? | See findings S1-S7 above; each is code-level and source-cited. |
