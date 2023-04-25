# QMD v2.1.0 — Security Review

| Field         | Value                                                                                                       |
| ------------- | ----------------------------------------------------------------------------------------------------------- |
| Subject       | [tobi/qmd](https://github.com/tobi/qmd) @ `v2.1.0`                                                          |
| Pinned commit | `65cd1b3fd02891d1ee0eefa751620918664fa321`                                                                  |
| Vendored at   | `research/qmd/`                                                                                             |
| Analyst       | claude-opus-4.7, effort=xhigh                                                                               |
| Method        | Static, read-only review per CLAUDE.md / AGENTS.md §3–§6. No code executed.                                |

This document answers CLAUDE.md §3.2 and §4.2. Each finding cites file +
line at the pinned commit. Categories that were reviewed and produced no
finding are recorded as **reviewed, no issues found**.

## B1. Threat model

QMD is intended to run **as the invoking user, on a single user's
machine, against the same user's markdown files**. Practical threats are
ranked under that assumption:

1. **Malicious or compromised configuration** — anyone who can write
   `~/.config/qmd/index.yml`, the per-collection YAML field, or the
   SQLite `store_collections.update_command` column reaches
   code-execution-as-the-user via `qmd update` (F-1).
2. **Malicious files inside an indexed tree** — a markdown file or
   filesystem symlink crafted to exfiltrate content via the index, or
   to crash the indexer.
3. **Local network adversary on the same machine** — a non-QMD
   process on the same loopback interface hitting the MCP HTTP server
   (F-3) or reading log files (F-4).
4. **Compromised third-party model registry** — a tampered GGUF on
   HuggingFace served on first download (F-6).
5. **Compromised dependency** — a transitive npm dependency used at
   runtime (F-5).

Out of scope by QMD's own design: hosted multi-tenant deployments,
network-exposed serving, multi-user shared state. None of those is a
shipped capability. This means several CLAUDE.md §4.2 questions are
answered with "by design, not applicable" — see §B11 below.

## B2. Findings

### F-1 — `qmd update` runs `bash -c <user-supplied>` (High, by-design)

**Cite.** `src/cli/qmd.ts:556-588`:

```ts
const yamlCol = getCollectionFromYaml(col.name);
if (yamlCol?.update) {
  console.log(`${c.dim}    Running update command: ${yamlCol.update}${c.reset}`);
  try {
    const proc = nodeSpawn("bash", ["-c", yamlCol.update], {
      cwd: col.pwd,
      stdio: ["ignore", "pipe", "pipe"],
    });
    ...
```

The `Collection.update` field (`src/collections.ts:33`) and the
`store_collections.update_command` column (`src/store.ts:811`) hold a
shell command string. When `qmd update` runs, QMD executes it via
`bash -c` with the collection's path as `cwd`. The intended use is
`update: 'git pull'`-style refresh of a notes vault before reindexing
(`research/qmd/README.md:751`,
`research/qmd/CLAUDE.md` "update [--pull]").

**Impact.** Whoever can write the YAML config (or the SQLite store_collections
table — both are inside `~/.cache/qmd/index.sqlite`) gets code execution
as the QMD-running user the next time `qmd update` is invoked. There is
no allow-list, no escape-checking, no sandboxing. On a user's own
machine this is the user's own data, but:

- A shared markdown vault committed to git could carry a
  `qmd-suggested` config in a sibling README and trick the user into
  installing it.
- Any other process that can write `~/.config/qmd/index.yml` (e.g. an
  attacker who escaped a different sandbox) escalates to full code
  execution at next `qmd update`.
- For us as adopters: shipping a feature that runs YAML-defined shell
  on user systems is an exception we'd have to call out in our threat
  model and security docs.

**Recommendation for indexit.** If we adopt QMD, **disable the
`update_command` path in our wrapper**. The cleanest patch is in our
CLI shim: refuse to call `bash -c` when `yamlCol.update` is set, or
ignore the field. The store schema can remain.

### F-2 — Symlinked file *contents* are indexed (Medium)

**Cite.** `src/store.ts:1189-1195` plus `src/store.ts:1207-1213`:

```ts
const allFiles: string[] = await fastGlob(globPattern, {
  cwd: collectionPath,
  onlyFiles: true,
  followSymbolicLinks: false,
  ...
});
...
for (const relativeFile of files) {
  const filepath = getRealPath(resolve(collectionPath, relativeFile));
  ...
  content = readFileSync(filepath, "utf-8");
```

`fast-glob` with `followSymbolicLinks: false` does **not** descend into
symlinked directories — but a symlinked *file* whose name matches the
glob (e.g. `notes/secret.md` → `~/.ssh/id_rsa.txt`) is returned. QMD
then resolves it through `realpathSync` (so the indexed path is the
target, not the link) and `readFileSync`'s the body into `content.doc`,
where it becomes searchable and retrievable via the SDK / MCP.

There is no containment check that `realpath(filepath)` is still a
descendant of the collection root.

**Impact.** Confidentiality. On a single-user laptop: low — same user.
On a shared host or in a scenario where one user opens another user's
notes tree, or where a notes tree is rsynced from an untrusted source,
a symlink can pull arbitrary readable files into the index and into
agentic/MCP responses.

**Recommendation.** If we ship QMD-derived code, add a containment
check: after `realpathSync`, assert the result starts with
`realpathSync(collectionPath)`. ~5 lines.

### F-3 — MCP HTTP transport: localhost, no auth (Medium)

**Cite.** `src/mcp/server.ts:796-799`:

```ts
await new Promise<void>((resolve, reject) => {
  httpServer.on("error", reject);
  httpServer.listen(port, "localhost", () => resolve());
});
```

The transport binds to the loopback interface with **no token, no
basic auth, no Origin / Host validation, no CORS**. Any local process
that can `connect(127.0.0.1, 8181)` can:

- Issue MCP `query` calls and exfiltrate the user's index contents
  (snippets, paths, full bodies via `multi_get` on a glob).
- DNS-rebind a browser at a malicious page so its JavaScript can
  POST `/query` (no Origin/Host check on `src/mcp/server.ts:637-794`).

The package documentation explicitly recommends running this for
"shared, long-lived" cases (`research/qmd/README.md:131-136`).

**Impact.** On a single-user dev box, low. On a multi-user or
DNS-rebinding-exposed laptop, medium — the index is intended to be
private, not "queryable by any local browser tab".

**Recommendation.** For our wrapper: keep stdio-MCP only by default,
or add a bearer token (`Authorization: Bearer …`) plus an `Origin: …`
allow-list before forwarding to the SDK. Both are <50 LOC.

### F-4 — HTTP MCP daemon logs query strings (Low)

**Cite.** `src/mcp/server.ts:608-624` and `src/cli/qmd.ts:3207`:

```ts
function describeRequest(body: any): string {
  ...
  if (args?.query) {
    const q = String(args.query).slice(0, 80);
    return `tools/call ${tool} "${q}"`;
  }
  ...
}
function log(msg: string): void {
  if (!quiet) console.error(msg);
}
```

The daemon variant pipes `console.error` to
`~/.cache/qmd/mcp.log` (`src/cli/qmd.ts:3203-3219`,
`logFd = openSync(logPath, "w")`, `stdio: ["ignore", logFd, logFd]`),
which truncates per daemon run. Up to 80 chars of every query string
land in the file. Queries can contain sensitive substrings — names,
project codes, password hints typed by mistake. The log inherits the
file mode from process umask.

**Impact.** Confidentiality. A different process on the same machine
that can read `~/.cache/qmd/mcp.log` (default umask 022 → world-readable
unless the user changed it) sees a rolling history of search queries.

**Recommendation.** For our wrapper: redact query strings, or chmod the
log to 0600 on creation.

### F-5 — No supply-chain audit step in CI (Low–Info)

**Cite.** `.github/workflows/ci.yml`, `.github/workflows/publish.yml`:

CI runs `npm install` / `bun install --frozen-lockfile` and tests.
There is no `npm audit`, no `osv-scanner`, no `socket`-style PR
gating, no SBOM emission. The publish workflow uses
`npm publish --provenance --access public`
(`.github/workflows/publish.yml:38-39`), which is good — npm
provenance attestation is the strongest practical signal that
`@tobilu/qmd@2.1.0` came from this repo's CI — but it does not vet
transitive dependencies.

**Impact.** Vulnerable transitive dependencies could ship to the
release without anyone noticing.

**Mitigations QMD already has.**
- All direct deps are pinned to exact versions
  (`research/qmd/package.json:48-72`; the `chore: pin all dependencies
  to exact versions` commit on 2026-04-05 was deliberate).
- `bun install --frozen-lockfile` in CI and release.
- `pre-push` hook validates that the tag matches `package.json` and
  that GitHub CI passed (`scripts/pre-push:30-88`).

**Recommendation.** For *our* CI consuming QMD: add `npm audit` /
`osv-scanner` steps over QMD's lockfile. Don't depend on upstream to
do this.

### F-6 — Model integrity is delegated; default model is on a personal HF account (Info)

**Cite.** `src/llm.ts:196-210, 239-307, 593-599`:

```ts
const DEFAULT_GENERATE_MODEL = "hf:tobil/qmd-query-expansion-1.7B-gguf/qmd-query-expansion-1.7B-q4_k_m.gguf";
...
async function getRemoteEtag(ref: HfRef): Promise<string | null> {
  const url = `https://huggingface.co/${ref.repo}/resolve/main/${ref.file}`;
  ...
  const resp = await fetch(url, { method: "HEAD" });
  ...
  const etag = resp.headers.get("etag");
  return etag || null;
}
...
private async resolveModel(modelUri: string): Promise<string> {
  this.ensureModelCacheDir();
  return await resolveModelFile(modelUri, this.modelCacheDir);
}
```

QMD's own ETag check is for cache freshness only — it overwrites the
local cache when ETag changes, and otherwise reuses what's there. The
actual blob fetch is delegated to `node-llama-cpp`'s
`resolveModelFile`. There is no SHA / signature check in QMD code.

The default *query-expansion* model is hosted under
`hf:tobil/qmd-query-expansion-1.7B-gguf/...`, i.e. the maintainer's
personal HuggingFace account (model card not pinned by hash from QMD's
side). The default *embedding* and *rerank* models are under
`ggml-org/...`, which is the well-known node-llama-cpp /
ggml-quantised mirror.

**Impact.** Anyone who compromises the maintainer's HF account, or HF
itself, can serve an altered query-expansion model on first install.
Because expansion only synthesises additional queries and is bounded
by a strict grammar (`src/llm.ts:1064-1071`), the worst plausible
outcome is search-quality degradation, not direct code execution from
the model itself. But a compromised *embedding* or *rerank* model
could subtly bias results in ways that are hard to detect.

**Recommendation.** For us: pin model URIs to a specific revision
(HF supports `@<commit>` syntax in their resolve URL) and verify a
known-good SHA on first download. ~15 LOC if we vendor the model
fetcher.

### F-7 — DDL with interpolated integer (Info)

**Cite.** `src/store.ts:1067-1069`:

```ts
db.exec("DROP TABLE IF EXISTS vectors_vec");
}
db.exec(`CREATE VIRTUAL TABLE vectors_vec USING vec0(hash_seq TEXT PRIMARY KEY, embedding float[${dimensions}] distance_metric=cosine)`);
```

`dimensions` is the embedding length returned by node-llama-cpp from
the loaded model (`src/store.ts:1485`). Not user input, but flagged
for completeness — there is one DDL string built by template literal.
If a future change takes `dimensions` from a less trusted source, this
becomes an injection point.

### F-8 — State-at-rest relies on umask (Info)

**Cite.** `src/store.ts:530-547`:

```ts
const cacheDir = process.env.XDG_CACHE_HOME || resolve(homedir(), ".cache");
const qmdCacheDir = resolve(cacheDir, "qmd");
try { mkdirSync(qmdCacheDir, { recursive: true }); } catch { }
return resolve(qmdCacheDir, `${indexName}.sqlite`);
```

`mkdirSync` does not pass a mode; `openDatabase` (`src/db.ts:62`) does
not chmod. The SQLite file, the `mcp.pid`/`mcp.log`, and the model
cache inherit process umask (commonly 022 → mode 644 / 755).
`content.doc` stores the **full body** of every indexed markdown file
verbatim. Anyone with read access to the user's `~/.cache/qmd/` has
a copy of all indexed notes.

**Impact.** Same-machine confidentiality only. Standard for
single-user dev tooling. Worth surfacing because the data is
sensitive-by-nature (private notes) yet not protected at the app
level.

**Recommendation.** If we ship a derivative, `chmod 0600` the SQLite
file on creation; `chmod 0700` the cache dir.

### F-9 — `execSync(\`git -C ${scriptDir} rev-parse --short HEAD\`)` (Info)

**Cite.** `src/cli/qmd.ts:2774`:

```ts
commit = execSync(`git -C ${scriptDir} rev-parse --short HEAD`, ...);
```

`scriptDir` is `dirname(fileURLToPath(import.meta.url))` — the
install path of QMD's own JS bundle. Not runtime-user input. Only an
issue if QMD is installed in a path containing shell metacharacters
(e.g. `/Users/foo/qmd build/`). The result is wrapped in
`try { … } catch { }`, so a failure is silently swallowed; the worst
outcome is the version banner missing the short SHA.

## B3. SQL injection — reviewed, no issues found

All user-controlled data flows into SQLite via `db.prepare(...).run(...)
/ .get(...) / .all(...)` with `?` placeholders. The grep at
`src/store.ts:898, 903, 909, 924, 936, 958, 964, 969, 974, 979, 984,
993, 999, 1001, 1014, 1027, 1030, 1042, 1054, 1107, 1379, 1860, 1877,
1879, 1901, 1907, 1926, 1935, 1944, 1968, 1974, 2064, 2080, 2099,
2115, 2130, 2138, 2146, 2333, 2344, 2359, 2477, 2497, 2544, 2573,
2576, 2596, 2612` and across `searchFTS` / `searchVec` confirms this.

`db.exec(...)` is used only for DDL, transaction management
(`migrate-schema.ts`), or vector table cleanup; the string content is
either a constant or a model-derived integer (F-7).

The two near-misses both turn out OK on inspection:

- `findDocument` uses `LIKE \`%${filepath}\`` — but `filepath` is bound
  as a parameter (`.get(\`%${filepath}\`)`), and the `%` is added
  in JS, not in SQL (`src/store.ts:3438`). User-controlled `LIKE`
  wildcards inside the bound value are intended fuzzy-match
  behaviour.
- `getEmbeddingDocsForBatch` builds `WHERE hash IN (${placeholders})`
  — but `placeholders` is `batch.map(() => "?").join(",")`, a
  controlled string of literal `?` characters
  (`src/store.ts:1378-1383`).

## B4. FTS5 query injection — reviewed, no issues found

All FTS5 queries are constructed by `buildFTS5Query`
(`src/store.ts:2822-2902`). Every term is fed through
`sanitizeFTS5Term` which strips everything except
`\p{L}\p{N}'_` (`src/store.ts:2777-2779`). Operators (`AND`, `NOT`,
prefix `*`, phrase quotes) are emitted by QMD's parser, not the
user, so the user cannot inject `OR`, `MATCH`, column-name selectors,
or unmatched quotes. Searches go through `searchFTS`
(`src/store.ts:2927`), `hybridQuery` (`src/store.ts:3906`), and
`structuredSearch` (`src/store.ts:4302`); the only entry point is the
sanitiser.

## B5. Path traversal — reviewed, mostly safe

Two paths to consider: indexing reads, and retrieval.

**Indexing reads** (`src/store.ts:1207-1213`) resolve relative paths
through `getRealPath = realpathSync` and `readFileSync`. The glob is
already rooted at `collectionPath`, but the `realpath` step can
*follow* a symlinked file to outside the collection — that's F-2.
For non-symlink content, fast-glob keeps results inside `cwd`.

**Retrieval** through `findDocument` (`src/store.ts:3386-3489`) and
`getDocumentBody` (`src/store.ts:3495-3539`) is database-only — both
functions take a path string and SELECT against the `documents` table.
A malicious caller cannot pass `../../etc/passwd` to read the file
system; they can only retrieve documents that are already indexed.
`multi_get` likewise globs against the database, not the filesystem
(`src/store.ts:3545-3617`). For our purposes this means QMD-as-MCP
**cannot be tricked into reading off-corpus files at query time** —
the corruption window is at indexing time only, and it's F-2.

## B6. Trust boundaries and input validation

| Boundary                          | Validation                                                                                                  | Notes                                                                                                                  |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| YAML config → QMD                 | `YAML.parse` (`src/collections.ts:163`) wrapped in try/catch. No schema validation of fields beyond shape.  | `update_command` accepted as-is (F-1). `editor_uri` template substitution is `replace(/\{path\}/g, ...)` etc. — never `eval`'d. |
| Env vars → QMD                    | `QMD_EMBED_MODEL` etc. accepted as literal strings, passed to node-llama-cpp's `resolveModelFile`.          | Mismatched dimensions are guarded with a clear error (`src/store.ts:1061-1066`).                                       |
| MCP request → QMD                 | `zod` schemas on tool input (`src/mcp/server.ts:227-316, 371-376, 437-442, 510`). String length, types enforced. | `query` content goes to FTS sanitiser / vector embed (both safe). `path` argument flows into `findDocument` (DB-only). |
| HTTP `/query` body → QMD          | `JSON.parse(rawBody)` then `String(s.query || "")` coercion (`src/mcp/server.ts:653-667`). Field-shape check only. | No size cap on body. Worth a `Content-Length` limit if exposed beyond loopback.                                        |
| File contents → indexer           | None beyond the FTS5 sanitiser at query time. Bodies are stored verbatim.                                   | Markdown is treated as opaque text; no HTML rendering, no JS evaluation.                                                |
| Editor URI template → terminal    | `encodeURI` on path; integer line/col (`src/cli/qmd.ts:1870-1912`). Wrapped in OSC 8 (`termLink`).           | `encodeURI` percent-encodes C0 control bytes including `\x07` and `\x1b`, so a malicious *path* cannot break the OSC 8 sequence. The template itself comes from env/YAML (user-controlled). |

## B7. Patch cadence and maintainer track record

`git log` over the pinned tree shows:

- **432 total commits**, first commit `2025-12-07` (`Initial commit:
  QMD - Quick Markdown Search`), `v2.1.0` released `2026-04-05`. So
  ~5 months of development at high cadence (~85 commits / month).
- Author distribution from `git log --pretty='%aN' | sort | uniq -c`:
  Tobi Lutke / Tobias Lütke / Tobi Lütke = 217 + 66 + 48 = **331
  commits (~77%)**; the next contributor has 6 commits. Bus factor is
  1 by any reasonable measure.
- Recent v2.1.0 work explicitly addresses dependency hygiene: `chore:
  pin all dependencies to exact versions`, `chore: sync bun.lock with
  pinned dependencies`, both on the release day.
- No public CVE / security advisory has been issued for `@tobilu/qmd`
  at v2.1.0 (checked by absence; not in the GHSA database under
  `tobi/qmd` as of pinning). Treat this as "no published incidents",
  not "no incidents".

For an `adopt` decision, this maintainer profile is acceptable but
fragile — see `applicability.md` §C6.

## B8. Multi-tenant / multi-user data isolation — by design, not applicable

QMD is single-process, single-user. There is no concept of "tenant",
no auth subsystem, no per-user view. The DB file is whoever runs the
process. This is a **non-finding**: the design is "personal tool";
multi-tenant isolation is *out of scope* upstream. For us, it would
become a finding the moment we exposed QMD via a network surface — at
which point F-3 becomes a real exposure rather than a local one.

## B9. Encryption — by design, not applicable

QMD does not encrypt data at rest (F-8 instead notes the umask
weakness). At-transit is moot for the local-only data path; for the
HF model fetch, node-llama-cpp uses HTTPS by default
(URL is `https://huggingface.co/...` in `src/llm.ts:240`). QMD does
not implement TLS itself. **Reviewed, deliberate omission.**

## B10. Sandboxing of user `update:` commands — none, by design

There is no resource limit, syscall filter, or chroot around the
`bash -c <update_command>` execution; the child inherits the QMD
process environment and runs in the collection root
(`src/cli/qmd.ts:559-562`). Hard to fix without breaking the feature.
For our wrapper: just don't expose this surface (F-1 mitigation).

## B11. CLAUDE.md §4.2 — explicit answers

1. **Authentication / authorization model?** — None. QMD authenticates
   to nothing because there is no remote endpoint. The MCP HTTP
   transport relies on loopback binding alone (F-3).
2. **Trust boundaries and input validation at each?** — See §B6.
3. **Secrets and credentials provisioning, storage, rotation?** — QMD
   itself handles no secrets. CI uses `NPM_TOKEN` and `GITHUB_TOKEN`
   from GitHub Actions secrets for publish; none of those land in the
   shipped artefact (`publish.yml:40-57`). User configs may contain
   shell commands (F-1) but no credentials by design.
4. **Multi-tenant / multi-user isolation?** — N/A by design (§B8).
5. **Data encryption at rest / in transit?** — No at-rest encryption
   (§B9, F-8). HF download is HTTPS via node-llama-cpp.
6. **What is logged?** — CLI prints to stdout/stderr; HTTP MCP
   daemon logs to `~/.cache/qmd/mcp.log` including ~80 char query
   prefixes (F-4) and session IDs. No body content logged. No
   structured logger; relies on `console.error`.
7. **Patch / release cadence and maintainer response history?** —
   §B7. Active maintainer; high cadence; bus factor 1; no published
   CVEs.
8. **Concrete risks our scan surfaced beyond CVE / OSV / Dependabot?**
   — F-1, F-2, F-3, F-4, F-6, F-8 above (the others are info-level).
   None of them appear in any public vulnerability database; all
   are behaviours of the v2.1.0 codebase.

## B12. Summary table

| ID  | Severity                  | Category                    | File:line                                            | Status               |
| --- | ------------------------- | --------------------------- | ---------------------------------------------------- | -------------------- |
| F-1 | High *(by-design)*        | Local code execution        | `src/cli/qmd.ts:556-588`, `src/store.ts:811`         | Mitigate in our wrapper |
| F-2 | Medium                    | Indirect file disclosure    | `src/store.ts:1189-1213`                             | Patch (containment check) |
| F-3 | Medium                    | Trust boundary (HTTP MCP)   | `src/mcp/server.ts:796-799`, `:637-794`              | Disable / token in wrapper |
| F-4 | Low                       | Logging                     | `src/mcp/server.ts:608-624`, `src/cli/qmd.ts:3203-3219` | Redact / chmod      |
| F-5 | Low–Info                  | Supply chain                | `.github/workflows/ci.yml`                           | Add audit in our CI  |
| F-6 | Info                      | Model integrity / trust path | `src/llm.ts:196-210`                                 | Pin / verify in wrapper |
| F-7 | Info                      | DDL with interpolated int   | `src/store.ts:1069`                                  | Watch for future changes |
| F-8 | Info                      | State-at-rest umask only    | `src/store.ts:530-547`, `src/db.ts:62`               | chmod 0600 in wrapper |
| F-9 | Info                      | execSync (version banner)   | `src/cli/qmd.ts:2774`                                | Cosmetic             |

## B13. What we did not find

The following were specifically searched and **no concern surfaced**:

- SQL injection (§B3).
- FTS5 query injection (§B4).
- Path traversal at retrieval / search time (§B5; only F-2 at indexing).
- Deserialisation gadgets — QMD uses `JSON.parse` on its own LLM cache
  values and on HTTP request bodies; no `pickle`, no `eval`, no
  `Function()`, no YAML custom-tag handlers (the `yaml` package is
  used in default safe mode in `src/collections.ts:163`).
- Prototype pollution sinks — QMD does not merge user JSON into
  prototypes anywhere I could find via grep on `Object.assign`,
  `__proto__`, `constructor`.
- XSS — QMD is a CLI / SDK / MCP server; it never renders HTML. The
  one place it emits ANSI-style escapes is `termLink` (OSC 8), where
  `encodeURI` neutralises control bytes in paths
  (`src/cli/qmd.ts:1870-1916`).
- Open redirects / SSRF — only one outbound HTTP call: HEAD to
  HuggingFace at a hard-coded `https://huggingface.co/.../resolve/main/...`
  URL (`src/llm.ts:240`). No URL is constructed from user input.
