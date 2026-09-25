# Obsidian-brain RAG — Design

Date: 2026-09-10
Status: draft for Jason review
Repo: `C:/Users/bottl/hermes-custom/RAG`
Vault: `https://github.com/bottlefedchaney808/obsidian-brain.git` (clone `C:/Users/bottl/obsidian-vault`)

## 1. Purpose

Retrieval over the Obsidian brain (and swept Hermes sessions) so Hermes can answer with **cited snippets**:

- What did I know? When? Why did I believe it? How did thinking change?

The vault is the memory. The LLM is a reasoning layer on top. Not training. Not a second fact store.

v1 success: correct note retrieved, strong source grounding, fast, historical filters, low hallucination. Not “biggest model / most embeddings.”

## 2. Non-goals (v1)

- Fine-tuning
- Qdrant / graph / auto-taxonomy / metadata LLM
- Trading coach, thesis builder, timeline products (those are queries on top of retrieval)
- Replacing Mem0 (single memory-provider rule; Mem0 stays)
- Patching `hermes-agent` core
- Local embedding models (Nous Portal embeddings only)
- Agents freely `write_file`-ing vault legs
- Dumping full tool JSON into git

## 3. Decisions locked

| Topic | Decision |
|---|---|
| Surface | Hermes **unified plugin** (`brain-rag`): desktop pane + `plugin_api.py` + agent tools `rag_search` / `rag_index` |
| Memory provider | **Do not.** Would replace Mem0 |
| Embeddings | Nous Portal `/v1/embeddings` (pin model id from live catalog at implement time) |
| Index | Local SQLite: FTS5 (BM25) + sqlite-vec. Not in git |
| Corpus v1 | Vault markdown + swept sessions. PDFs/repos later |
| Sessions | Newest stay in Hermes `state.db`. Weekly sweep into vault git |
| Vault writers | **Sweep** and **explicit remind** only |
| MEMORY.md | Pointer index only |
| Legs | Construction / Development / Trading — filterable, no mix |

## 4. Architecture

Develop in this repo. **Do not run from here.** Runtime is profile-scoped Hermes home.

Unified package (SDK: [Desktop Plugin SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk) — “One package, both SDKs”):

```
$HERMES_HOME/plugins/brain-rag/
├── plugin.yaml                 # agent tools: rag_search, rag_index
├── dashboard/
│   ├── manifest.json           # {"name":"brain-rag","api":"plugin_api.py"}
│   └── plugin_api.py           # /api/plugins/brain-rag/{search,index,status}
└── desktop/
    └── plugin.js               # @hermes/plugin-sdk pane + ctx.rest
```

`$HERMES_HOME` is profile-scoped:

| Profile | Plugin root |
|---|---|
| default | `%LOCALAPPDATA%/hermes/plugins/brain-rag/` |
| named | `%LOCALAPPDATA%/hermes/profiles/<name>/plugins/brain-rag/` |

Deploy copies the same tree to **every profile that should have RAG**. Desktop Settings → Plugins enable is **not** the Python gate; `plugins.enabled` in that profile’s `config.yaml` must list `brain-rag` or `ctx.rest` 405s.

Index file: `$HERMES_HOME/rag/brain.sqlite` (per profile). Not in the vault repo. Profiles do not share an index.

```
vault (git) ──┐                    Nous /v1/embeddings
hot sessions ─┼── indexer ── SQLite (FTS5 + vectors)
weekly sweep ─┘         │
                        ▼
              rag_search / rag_index
              desktop pane via ctx.rest
```

## 5. Intake — only two vault doors

| Door | When | What |
|---|---|---|
| **Sweep** | weekly cron | Organizes holding pen → leg notes + session markdown. The organizer. |
| **Explicit remind** | Jason says “put this in the brain” | Thin note, correct leg, now |

**Not a door:** ad-hoc agent writes into Construction/Development/Trading, MEMORY.md fact dumps, git-stashing vault dirt, Inbox.md novels.

**Holding pen (not git until sweep):**

- Hot: Hermes `state.db` (newest sessions)
- Cold exports: `C:/Users/bottl/hermes-salvage-20260909/session-exports/` (until a dedicated intake dir is wired)

Sweep pull-rebase’s the vault clone, writes organized files, commit+push. If push fails, commit stays local and the job reports. If sweep fails, hot sessions remain in `state.db`; vault unchanged.

## 6. Vault layout (sessions)

One note, one leg. No top-level `Sessions/`.

```
Construction/Sessions/YYYY-MM-DD-<short-id>.md
Development/Sessions/YYYY-MM-DD-<short-id>.md
Trading/Sessions/YYYY-MM-DD-<short-id>.md
```

Frontmatter:

```yaml
---
type: session
leg: Development
profile: default
session_id: 20260809_151112_f2ff66
started: 2026-08-09
source: desktop
---
```

Body: user/assistant turns as markdown. **Drop tool JSON.** Artifact paths as wikilinks or path strings.

Leg assignment from session cwd:

| cwd / workspace | leg |
|---|---|
| Tiferet / construction repos | Construction |
| FinancialDevelopment / Trading | Trading |
| hermes / obsidian / unknown | Development |

One file per swept session (not weekly bundles).

Regular notes stay where they are. Preserve original notes; never replace with summaries.

## 7. Chunking

**Notes:** split on `##` and deeper. Heading path + note title + folder + tags + frontmatter + mtime travel with the chunk. No-heading notes = one chunk; if huge, split on blank lines (~1500 token cap). Do not split a short heading away from its body.

**Sessions:** one chunk = one user turn + following assistant reply.

**Skip:** `.obsidian/`, `.git/`, binaries under `Attachments/`, raw tool dumps.

Wikilinks stay in chunk text. `leg` = first path segment.

Indexer keys on `(path, heading_or_turn, content_hash)`. Unchanged files skipped.

## 8. Retrieval

`rag_search(query, leg=all, after=None, before=None, source=all, k=8)`

1. Embed query via Nous.
2. FTS5 BM25 on chunk text.
3. Vector kNN on sqlite-vec.
4. Apply filters: `leg`, date window (`after`/`before` on note mtime or session `started`), `source` (`note` \| `session` \| `all`), optional path/tag.
5. Merge with **reciprocal rank fusion**.
6. Return pack: `text`, `path`, `heading`, `score`, `date`, `leg`, `source`, `wikilinks`, `session_id?`.

Citations required on every hit (path + heading or session id + date + leg). Empty pack → `{hits: []}`; the agent must not invent.

No auto-inject into the system prompt. Tools are on-demand. Mem0 prefetch unchanged.

No reranker in v1.

Time-aware v1 = date filters, not snapshots of the whole vault.

## 9. Tools

**`rag_search`** — parameters above; JSON `{hits: [...]}` or `{error: "..."}`.

**`rag_index`** — `{mode: "incremental"|"full"}`. Pulls vault if needed, embeds new/changed chunks, writes sqlite.

Desktop pane: search box, leg filter, hit list with path + snippet; `ctx.rest('/search')`. No secrets in renderer.

## 10. Errors (fail closed)

| Failure | Behavior |
|---|---|
| Nous embeddings down | BM25-only; hits tagged `vector=skipped` |
| Vault clone missing / pull failed | Do not index; `rag_search` errors |
| Sweep fails | Hot sessions stay in `state.db`; vault untouched |
| Plugin not in `plugins.enabled` | Pane disabled, tools absent; no silent fallback |
| Plugin missing on a profile | That profile has no RAG; do not borrow another index |
| Corrupt SQLite | Refuse search; do not wipe |
| No hits | `{hits: []}` |

## 11. Eval gate (ship blocker)

Wrong-leg leak or citation-less pack = **fail**, not a warning.

**Unit:** chunker, FTS, RRF, leg/date filters, skip-rules.

**Golden set** (retrieve the right note, correct leg, citation present):

1. Why did I stop using strategy X?
2. What are my strongest risk-management conclusions?
3. What lessons repeatedly appear after losses?
4. What indicators do I trust most?
5. What recurring themes exist across successful trades?
6. What mistakes do I repeatedly make?
7. What are my best trading insights about volatility?
8. How has my thinking on factor investing changed over time?
9. What did I believe before drawdown Y?
10. Find observations about earnings reactions.

Fixture tests use a tiny fake vault (Construction vs Trading leak). Golden questions run against the real clone in a local-only eval, not CI.

No coach/timeline features until this gate is green.

## 12. MEMORY.md

Keep tiny. Pointers only (`[[Jason]]`, `[[Hermes]]`, skill catalog). Durable facts live in the vault **after** sweep or explicit remind. RAG is how the agent finds them instead of stuffing MEMORY.md.

## 13. Implementation notes

- Language: Python indexer + FastAPI `plugin_api.py`; desktop `plugin.js` is uncompiled ESM (`jsx()`, no JSX syntax).
- Auth for embeddings: reuse Hermes Nous OAuth (`~/.hermes/auth.json`); never put tokens in plugin.js or vault.
- Sweep is a Hermes cron on profile `default`.
- `hermes sessions prune` **deletes**; it is not intake. Export path is `hermes sessions export` → holding pen → sweep.
- Reference docs: Hermes `llms.txt` plugin + desktop SDK pages; vault `Development/Hermes Desktop plugins.md` (profile-scoped roots).

## 14. Later (not v1)

PDFs, git repos, wikilink graph expansion, Qdrant, reranker, auto-classification, coach/timeline UIs.
