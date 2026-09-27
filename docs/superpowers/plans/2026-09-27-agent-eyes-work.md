# Agent Eyes Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Agent Eyes show `cant-embed` instead of a blank pane, and install the agent plugin on the `gork` profile via fleet.

**Architecture:** Keep the existing split desktop + agent plugin. Add `Gaze.embed` from an agent-side HTTP header probe so the desktop does not guess from iframe `load` events. Patch `plugin.js` so `$cantEmbed` exists, is subscribed, and is not cleared every poll. Declare `gork` in `fleet.yaml` and split `agent-eyes` into its own package (`default`+`jason`+`gork`) so `texting-style` does not land on gork.

**Tech Stack:** Hermes desktop plugin (single ESM `plugin.js`), Python agent plugin, node:test, pytest, fleet CLI.

**Spec:** `C:\Users\bottl\hermes-custom\docs\superpowers\specs\2026-09-27-agent-eyes-work.md`

## Global Constraints

- Plugin id: `agent-eyes`. Display name: **Agent Eyes**.
- ASCII-only `plugin.js`; three static imports only; `node --check` must pass.
- Gaze file: `$HERMES_HOME/cache/agent-eyes/gaze.json`.
- Tools: `eyes_open`, `eyes_close` only.
- Never hand-edit any `config.yaml`. Use `./fleet.cmd` and `hermes plugins enable` without `--allow-tool-override`.
- Not tiferet. Not texting-style on gork. Not orgo enable.
- Do not run the plugin from the git checkout in production — fleet materializes.
- Windows host: `./fleet.cmd` from `C:\Users\bottl\hermes-custom`. Pytest via `py -3.12`. Native paths for native tools (`C:/Users/bottl/...`).
- Nested git: plugin edits commit in `hermes-bot-kit/` if that repo is dirty; `fleet.yaml` + docs commit on `hermes-custom`. Do not push.
- After live-path Python edits: wipe `__pycache__` and kill that profile’s `hermes --profile <name> serve`.

---

## File map

| Path | Responsibility |
|---|---|
| `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/gaze.py` | `probe_embed`, `embed` field on gaze |
| `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/tools.py` | return `embed` from `eyes_open` |
| `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/tests/test_gaze.py` | empty_gaze + probe tests |
| `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/tests/test_tools.py` | eyes_open returns embed |
| `hermes-bot-kit/agent-eyes/plugin.js` | cant-embed atom, phase, poll, iframe |
| `hermes-bot-kit/agent-eyes/plugin.test.mjs` | phaseForGaze blocked + applyIframeSrc |
| `hermes-bot-kit/agent-eyes/README.md` | gork + example.com is cant-embed |
| `fleet.yaml` | gork profile + split agent-eyes package |
| `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/dashboard/plugin_api.py` | no schema change required (returns gaze dict as-is) |

---

### Task 1: Gaze `embed` field + probe (agent)

**Files:**
- Modify: `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/gaze.py`
- Modify: `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/tests/test_gaze.py`
- Modify: `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/tools.py`
- Modify: `hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes/tests/test_tools.py`

**Interfaces:**
- Consumes: existing `allow_url` / `open_url` / `empty_gaze`
- Produces: `probe_embed(url: str, timeout: float = 3.0) -> str` returning `"ok" | "blocked" | "unknown"`; `empty_gaze` includes `"embed": "unknown"`; `open_url` writes `embed`; `close_url` resets `embed` to `"unknown"`; `eyes_open` JSON includes `"embed"`

- [ ] **Step 1: Write failing tests** in `test_gaze.py`

Add to `test_empty_gaze_shape` expected dict:

```python
        "embed": "unknown",
```

Add (keep existing tests; only extend this file):

```python
from gaze import probe_embed, EMBED_OK, EMBED_BLOCKED, EMBED_UNKNOWN


class _FakeResp:
    def __init__(self, headers, status=200):
        self.headers = headers
        self.status = status
        self.url = "https://example.com/"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=0):
        return b""


def test_probe_embed_deny(monkeypatch):
    def fake_open(req, timeout=3.0):
        return _FakeResp({"X-Frame-Options": "DENY"})

    monkeypatch.setattr("gaze.urlopen", fake_open)
    assert probe_embed("https://example.com/") == EMBED_BLOCKED


def test_probe_embed_sameorigin(monkeypatch):
    def fake_open(req, timeout=3.0):
        return _FakeResp({"x-frame-options": "sameorigin"})

    monkeypatch.setattr("gaze.urlopen", fake_open)
    assert probe_embed("https://example.com/") == EMBED_BLOCKED


def test_probe_embed_frame_ancestors_none(monkeypatch):
    def fake_open(req, timeout=3.0):
        return _FakeResp({"Content-Security-Policy": "frame-ancestors 'none'"})

    monkeypatch.setattr("gaze.urlopen", fake_open)
    assert probe_embed("https://example.com/") == EMBED_BLOCKED


def test_probe_embed_ok_when_no_headers(monkeypatch):
    def fake_open(req, timeout=3.0):
        return _FakeResp({})

    monkeypatch.setattr("gaze.urlopen", fake_open)
    assert probe_embed("https://example.com/") == EMBED_OK


def test_probe_embed_unknown_on_error(monkeypatch):
    def fake_open(req, timeout=3.0):
        raise TimeoutError("nope")

    monkeypatch.setattr("gaze.urlopen", fake_open)
    assert probe_embed("https://example.com/") == EMBED_UNKNOWN


def test_open_url_writes_embed(monkeypatch):
    monkeypatch.setattr("gaze.probe_embed", lambda url, timeout=3.0: "blocked")
    doc = open_url("https://example.com/", title="t")
    assert doc["embed"] == "blocked"
    assert read_gaze()["embed"] == "blocked"
```

In `test_tools.py` extend `test_eyes_open_ok` (or add):

```python
def test_eyes_open_returns_embed(monkeypatch):
    monkeypatch.setattr(gaze, "probe_embed", lambda url, timeout=3.0: "blocked")
    raw = tools.eyes_open({"url": "https://example.com/", "title": "t"})
    body = json.loads(raw)
    assert body["ok"] is True
    assert body["embed"] == "blocked"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd C:/Users/bottl/hermes-custom/hermes-bot-kit/agent-eyes/agent-plugin
PYTHONPATH=agent-eyes py -3.12 -m pytest agent-eyes/tests/test_gaze.py agent-eyes/tests/test_tools.py -q --import-mode=importlib
```

Expected: FAIL (`embed` missing / `probe_embed` not defined). If `py -3.12` missing, use a Python that has pytest (not Hermes tools python).

- [ ] **Step 3: Implement in `gaze.py`**

Keep existing helpers. Add near the top with the other constants:

```python
EMBED_OK = "ok"
EMBED_BLOCKED = "blocked"
EMBED_UNKNOWN = "unknown"
```

Export `urlopen` as a module attribute so tests can monkeypatch it:

```python
from urllib.request import Request, urlopen as _urlopen

urlopen = _urlopen
```

`empty_gaze` must include `"embed": EMBED_UNKNOWN`.

`read_gaze` copies `embed` if it is one of the three literals, else `"unknown"`.

Add:

```python
def _csp_frame_ancestors(header: str) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        chunk = part.strip()
        if chunk.lower().startswith("frame-ancestors"):
            return chunk[len("frame-ancestors") :].strip().lower()
    return None


def probe_embed(url: str, timeout: float = 3.0) -> str:
    if not isinstance(url, str) or not url:
        return EMBED_UNKNOWN
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgentEyes/1.0",
        "Accept": "*/*",
    }
    last_err = None
    for method in ("HEAD", "GET"):
        try:
            req = Request(url, method=method, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                xf = (resp.headers.get("X-Frame-Options") or "").strip().lower()
                if xf in ("deny", "sameorigin"):
                    return EMBED_BLOCKED
                csp = resp.headers.get("Content-Security-Policy") or ""
                csp_ro = resp.headers.get("Content-Security-Policy-Report-Only") or ""
                for raw in (csp, csp_ro):
                    fa = _csp_frame_ancestors(raw)
                    if fa is None:
                        continue
                    if fa in ("'none'", "none") or fa in ("'self'", "self"):
                        return EMBED_BLOCKED
                    if "*" in fa.split():
                        return EMBED_OK
                    return EMBED_BLOCKED
                return EMBED_OK
        except Exception as exc:  # timeout, HTTPError 405, URLError
            last_err = exc
            continue
    return EMBED_UNKNOWN
```

`open_url`: after allow_url succeeds, `embed = probe_embed(normalized)` then write it on the gaze dict.

`close_url`: set `embed` to `EMBED_UNKNOWN`.

Do not let probe exceptions escape `open_url`.

- [ ] **Step 4: `tools.py` `eyes_open` return**

Change the success payload to include `"embed": doc.get("embed") or "unknown"`. Keep `_as_args` dict dispatch as-is.

- [ ] **Step 5: Run tests — expect PASS**

Same pytest command as Step 2. Expected: PASS.

- [ ] **Step 6: Commit in hermes-bot-kit if that nested repo is git**

```bash
cd C:/Users/bottl/hermes-custom/hermes-bot-kit
git add agent-eyes/agent-plugin/agent-eyes/gaze.py agent-eyes/agent-plugin/agent-eyes/tools.py agent-eyes/agent-plugin/agent-eyes/tests/test_gaze.py agent-eyes/agent-plugin/agent-eyes/tests/test_tools.py
git commit -m "fix(agent-eyes): probe X-Frame-Options and store gaze.embed"
```

If hermes-bot-kit is not a separate git, stage those files on the parent instead.

---

### Task 2: Desktop cant-embed (no black box)

**Files:**
- Modify: `hermes-bot-kit/agent-eyes/plugin.js`
- Modify: `hermes-bot-kit/agent-eyes/plugin.test.mjs`

**Interfaces:**
- Consumes: `gaze.embed` from `/gaze`
- Produces: `$cantEmbed` atom; `phaseForGaze` returns `cant-embed` when `embed === 'blocked'`; iframe `src` not applied when blocked

- [ ] **Step 1: Extend `plugin.test.mjs` `__t` export**

The loader already exports `phaseForGaze` and `applyIframeSrc`. Add tests:

```javascript
test('phaseForGaze blocked embed is cant-embed', () => {
  const { t } = loadPlugin()
  const p = t.phaseForGaze({
    gaze: { url: 'https://example.com/', embed: 'blocked', title: 't', stills: [] }
  })
  assert.equal(p.phase, 'error')
  assert.equal(p.code, 'cant-embed')
})

test('applyIframeSrc refuses when blocked flag passed via allowUrl still ok — src only if allowed', () => {
  const { t } = loadPlugin()
  const calls = []
  const iframe = { getAttribute: () => '', setAttribute: (k, v) => calls.push([k, v]) }
  assert.equal(t.applyIframeSrc(iframe, 'https://example.com/'), true)
  assert.equal(t.applyIframeSrc(iframe, 'javascript:alert(1)'), false)
})
```

If you export `shouldShowLive(gaze, cantEmbed, phase)` from production via `__t`, test that `embed: 'blocked'` yields false. Prefer testing `phaseForGaze` which is already exported.

- [ ] **Step 2: Run `node --test hermes-bot-kit/agent-eyes/plugin.test.mjs` — expect FAIL** on the new phase test.

- [ ] **Step 3: Patch `plugin.js`**

`makeEngine` — add `$cantEmbed: atom(false)` to the returned object (and the `return { ... }` list).

`phaseForGaze`:

```javascript
function phaseForGaze(input) {
  if (input && input.httpStatus === 405) return { phase: 'error', code: 'no-plugin' }
  if (input && input.error) return { phase: 'error', code: 'unreachable' }
  const gaze = input && input.gaze
  if (!gaze || !gaze.url) return { phase: 'idle', code: 'idle' }
  const allowed = allowUrl(gaze.url)
  if (!allowed.ok) return { phase: 'error', code: 'unsafe-url' }
  if (gaze.embed === 'blocked') return { phase: 'error', code: 'cant-embed' }
  return { phase: 'looking', code: null }
}
```

`setGaze` already calls `phaseForGaze` — good.

`applyGazeToIframe`: if `gaze.embed === 'blocked'` or `!url`, return without setting src. If you must clear a previous src when switching to blocked, set `src` to `about:blank` **only if** current src is a real URL — `about:blank` is in the refused-scheme list for `allowUrl`, so do **not** go through `applyIframeSrc`. Use a dedicated `ifr.removeAttribute('src')` or `ifr.setAttribute('src', 'about:blank')` that does not pass `allowUrl`. Prefer `removeAttribute('src')`.

`pollOnce` — replace the `clearCantEmbed()` unconditional call:

```javascript
    const prevUrl = engine.$gaze.get() && engine.$gaze.get().url
    setGaze(g, ctx)
    if ((g.url || '') !== (prevUrl || '')) {
      clearCantEmbed()
    }
    if (g.embed === 'blocked') {
      setCantEmbed()
    }
    applyGazeToIframe(g)
```

Call `setGaze` **after** reading `prevUrl`. Current code calls `setGaze` first — capture prev before `setGaze`.

`AgentEyesPane`: add `const cantEmbed = useValue(engine.$cantEmbed)` and use `!!cantEmbed` instead of `isCantEmbed()` for `showLive`. Also `showLive` must be false when `g.embed === 'blocked'` or `phase.code === 'cant-embed'`.

Error overlay: give the ErrorState wrapper `style: { zIndex: 2 }` so it sits above the black slot.

`makeIframe`: keep create-once. Move load/error/timeout arming into `armIframeWatch(ifr)` and call it from `applyGazeToIframe` after a src change. On `load`, if `embed` is already blocked, keep cant-embed. Do not treat successful cross-origin `load` as cant-embed (contentDocument is null for both success and DENY). **Trust `gaze.embed`.** Timeout fallback only when `embed` is `unknown` and `load` never fired.

- [ ] **Step 4: ASCII + node check**

```bash
cd C:/Users/bottl/hermes-custom/hermes-bot-kit
node --check agent-eyes/plugin.js
python -c "p=open('agent-eyes/plugin.js','rb').read(); p.decode('ascii'); print('ascii-ok')"
node --test agent-eyes/plugin.test.mjs
```

Expected: `ascii-ok`, tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent-eyes/plugin.js agent-eyes/plugin.test.mjs
git commit -m "fix(agent-eyes): show cant-embed instead of a blank iframe"
```

---

### Task 3: Fleet — declare gork, split agent-eyes package

**Files:**
- Modify: `C:\Users\bottl\hermes-custom\fleet.yaml`
- Modify: `hermes-bot-kit/agent-eyes/README.md` (profiles line: default + jason + gork; example.com → cant-embed)

**Interfaces:**
- Consumes: existing fleet sync/enable
- Produces: `profiles.gork`; package `agent-eyes` with profiles `[default, jason, gork]`; `bot-kit-agent` without the agent-eyes surface

- [ ] **Step 1: Edit `fleet.yaml`**

Under `profiles:` after `tiferet` (or after `jason`), add:

```yaml
  gork:
    home: ~/.hermes/profiles/gork
    role: >-
      Grok-Powered Generalist (profile gork). Lab-adjacent, not company-facing.
      Gets Agent Eyes so the human can see what this bot is looking at.
```

In `bot-kit-agent`:
- Keep `profiles: [default, jason]`
- Remove the agent-plugin surface `from: agent-eyes/agent-plugin/agent-eyes`
- Keep orgo-computer `enable: false`
- Update summary/notes so they no longer claim agent-eyes lives in this package

Add a new package **immediately after** `bot-kit-agent` (before the upstream extras):

```yaml
  - name: agent-eyes
    source: hermes-bot-kit
    summary: >-
      Agent Eyes agent plugin — eyes_open / eyes_close + stills hook. Desktop
      half is global via bot-kit-desktop.
    profiles: [default, jason, gork]
    surfaces:
      - kind: agent-plugin
        from: agent-eyes/agent-plugin/agent-eyes
        install_as: agent-eyes
        enable: true
    notes: >-
      Not tiferet. Not texting-style. gork is included so this bot can show
      pages; do not fold gork into bot-kit-agent (that would install texting-style).
```

Fix comments that say the fleet has exactly three profiles if they would now be false. Do **not** add `gork` to tiferet-narrow packages, `bot-kit-agent`, or the upstream lab extras.

README: agent plugin on `default`, `jason`, and `gork`. Note that `https://example.com` is expected `cant-embed`.

- [ ] **Step 2: Dry run then apply**

```bash
cd C:/Users/bottl/hermes-custom
./fleet.cmd sync
./fleet.cmd sync --apply -k agent-eyes
./fleet.cmd enable agent-eyes --apply
./fleet.cmd status -v
```

Expected:
- `gork` appears under PROFILES
- `agent-eyes` CREATE/ok on default, jason, gork
- tiferet has no agent-eyes action
- `C:/Users/bottl/.hermes/profiles/gork/plugins/agent-eyes/plugin.yaml` exists (junction/symlink, not a frozen copy)

If sync wants to also install texting-style on gork, **stop** — you put gork on the wrong package.

- [ ] **Step 3: Doctor + dict smoke on gork home**

```bash
cd C:/Users/bottl/hermes-custom
hermes plugins doctor C:/Users/bottl/hermes-custom/hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes --ci

HERMES_HOME=C:/Users/bottl/.hermes/profiles/gork PYTHONPATH=C:/Users/bottl/hermes-custom/hermes-bot-kit/agent-eyes/agent-plugin/agent-eyes py -3.12 -c "import json,tools; print(tools.eyes_open({'url':'https://example.com','title':'t'}))"
```

Expected: doctor clean. JSON `ok: true` and `embed` of `blocked` or (only if probe cannot see headers) `unknown`. Then:

```bash
test -f C:/Users/bottl/.hermes/profiles/gork/cache/agent-eyes/gaze.json && echo gaze-ok
```

- [ ] **Step 4: Reload serve so live Bot Chat picks up code**

Wipe pycache:

```bash
rm -rf C:/Users/bottl/.hermes/plugins/agent-eyes/__pycache__ \
       C:/Users/bottl/.hermes/profiles/jason/plugins/agent-eyes/__pycache__ \
       C:/Users/bottl/.hermes/profiles/gork/plugins/agent-eyes/__pycache__
```

Kill per-profile serve processes for `jason`, `gork`, and default if running (they respawn on the next Bot Chat message). Do not kill the desktop app.

- [ ] **Step 5: Commit fleet.yaml + README + this docs tree on hermes-custom**

```bash
cd C:/Users/bottl/hermes-custom
git add fleet.yaml hermes-bot-kit/agent-eyes/README.md docs/superpowers/specs/2026-09-27-agent-eyes-work.md docs/superpowers/plans/2026-09-27-agent-eyes-work.md
git commit -m "feat(fleet): put agent-eyes on gork; split out of bot-kit-agent"
```

`hermes-bot-kit` may be a nested git — if `git add hermes-bot-kit/agent-eyes/README.md` fails, commit README in the nested repo instead.

---

### Task 4: Verification gate (do not skip)

Run all of these and paste the outputs into the final report:

```bash
cd C:/Users/bottl/hermes-custom/hermes-bot-kit
node --check agent-eyes/plugin.js
python -c "p=open('agent-eyes/plugin.js','rb').read(); p.decode('ascii'); print('ascii-ok')"
node --test agent-eyes/plugin.test.mjs

cd C:/Users/bottl/hermes-custom/hermes-bot-kit/agent-eyes/agent-plugin
PYTHONPATH=agent-eyes py -3.12 -m pytest agent-eyes/tests -q --import-mode=importlib

cd C:/Users/bottl/hermes-custom
./fleet.cmd status
ls -la C:/Users/bottl/.hermes/profiles/gork/plugins/agent-eyes
test ! -e C:/Users/bottl/.hermes/profiles/tiferet/plugins/agent-eyes && echo tiferet-clean
```

Done means: tests green, gork junction exists, tiferet has no agent-eyes, doctor passed, smoke JSON printed.

Tell Jason: reload desktop plugins (palette → Reload plugins) if the pane JS change does not appear; next `eyes_open https://example.com` on gork/jason/default should show **cant-embed** copy, not a black box. For a live iframe, open a URL that does not send X-Frame-Options DENY.
