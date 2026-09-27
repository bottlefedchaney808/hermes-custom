# Agent Eyes — make it work, put it on gork

Date: 2026-09-27
Status: approved (Jason: spec → plan → delegate to grok)
Repo: `C:\Users\bottl\hermes-custom`
Plugin tree: `hermes-bot-kit/agent-eyes/`
Original design (still in force except where this spec overrides): `C:\Users\bottl\.opencode\plan\2026-09-26-agent-eyes-design.md`

## 1. What Jason asked

1. Agent Eyes was installed and **never actually showed anything**.
2. Put it on **one more profile: `gork`**.
3. Spec + plan here, then Grok Build CLI implements.

## 2. Live evidence (do not re-litigate)

| Fact | Proof |
|---|---|
| Agent plugin exists on `default` and `jason` | `~/.hermes/plugins/agent-eyes/plugin.yaml`, `~/.hermes/profiles/jason/plugins/agent-eyes/plugin.yaml` |
| Desktop pane exists (global) | `~/.hermes/desktop-plugins/agent-eyes/plugin.js` |
| `gork` has **no plugin tree** | `~/.hermes/profiles/gork/plugins/agent-eyes` does not exist. That profile’s `plugins/` only has `bot-forge-marks`. |
| `gork` config already lists `agent-eyes` in `plugins.enabled` | `~/.hermes/profiles/gork/config.yaml` line 228 — enabled without files. |
| `fleet.yaml` does **not** declare `gork` | `profiles:` is only `default`, `jason`, `tiferet`. `bot-kit-agent` profiles: `[default, jason]`. |
| `eyes_open` dict-dispatch is **already fixed in source** | `tools.py` `_as_args`; jason `errors.log.1` 2026-09-26 08:45 `AttributeError: 'dict' object has no attribute 'strip'` is the old bug. Later room log: tool returned ok. |
| The remaining product bug is a **blank pane** | Room log: “its up above us in this room its been blank” / “its not throwing but I dont see anything either”. Test URL was `https://example.com` which sends `X-Frame-Options: DENY`. |

## 3. Why the pane is blank (root cause)

`plugin.js` treats a gaze URL as “show live iframe”. `example.com` (and most public sites) refuse framing. Spec already required `cant-embed` instead of a black box. Current code fails that:

1. `makeEngine()` never creates `$cantEmbed`, but `setCantEmbed` / `isCantEmbed` call `engine.$cantEmbed.*`.
2. `AgentEyesPane` does not `useValue(engine.$cantEmbed)`, so even a working atom would not re-render.
3. `pollOnce` calls `clearCantEmbed()` on **every** 500ms poll, wiping the flag.
4. `makeIframe` arms `load`/`error`/`8s timeout` **once**. Cross-origin X-Frame DENY still fires `load` (empty document), so the timeout never sets cant-embed. `error` does not fire.
5. `eyes_open` always returns `"embed": "unknown"` and never writes an embed verdict onto `gaze.json`, so the desktop cannot know the page is unlistenable without guessing from iframe events (which lie).

Acceptance in the original design was self-contradictory: “`eyes_open https://example.com` → pane shows it” **and** “DENY X-Frame-Options → `cant-embed`”. `example.com` **is** DENY. This spec resolves that: example.com must show **cant-embed + Open in browser**, never a blank iframe. A different, actually-embeddable URL is the “shows the page” case.

## 4. Product rules (locked)

- Plugin id / folder: `agent-eyes`. Display name: **Agent Eyes**.
- Tools: `eyes_open`, `eyes_close` only. Stills via `pre_llm_call` + DOM backup. No `eyes_show`.
- Gaze file: `$HERMES_HOME/cache/agent-eyes/gaze.json` (per profile). Not a Python global.
- URL allowlist unchanged (http(s) only; http only private hosts).
- Iframe sandbox unchanged. Thumbnail pointer-events none. Expand moves the same iframe node.
- **Never a black box.** If the page will not embed, show `cant-embed` chrome (title/body from existing `ERRORS['cant-embed']`) and keep the URL for Open in browser.
- Do **not** enable on `tiferet`.
- Do **not** dump lab plugins or `texting-style` onto `gork`. Only the agent-eyes agent plugin.
- Desktop plugin is already global — do not reinstall it into a profile folder.
- Never hand-edit any profile `config.yaml`. Use `fleet enable` / `hermes config set` / `hermes plugins enable`.
- ASCII-only `plugin.js`; exactly three static imports; `node --check` must pass.
- Nested git: `hermes-bot-kit/` is its own repo. Plugin code commits there. `fleet.yaml` + this spec/plan commit on `hermes-custom`. Do not push.

## 5. Gaze document — add `embed`

```
Gaze.embed: "unknown" | "ok" | "blocked"
```

- `empty_gaze` includes `"embed": "unknown"`.
- `open_url` probes the URL (see §6) and stores the verdict.
- `close_url` resets `embed` to `"unknown"`.
- `read_gaze` defaults missing `embed` to `"unknown"`.
- Tools return the same `embed` value they wrote.

## 6. Embed probe (agent side)

New `gaze.probe_embed(url: str, timeout: float = 3.0) -> str`:

- Only called after `allow_url` accepts.
- Try `HEAD`, fall back to `GET` if HEAD is 405/501 or otherwise unusable. Timeout 3s. No cookies. Follow redirects (max 5). User-Agent a normal desktop browser string.
- **blocked** if final response has:
  - `X-Frame-Options` of `DENY` or `SAMEORIGIN` (case-insensitive; `SAMEORIGIN` cannot match the desktop origin), or
  - `Content-Security-Policy` / `Content-Security-Policy-Report-Only` `frame-ancestors` that is `'none'` or `'self'` only (no `*`, no the desktop origin).
- **ok** if those headers are absent or `frame-ancestors` includes `*`.
- **unknown** on network error, timeout, or missing headers that are inconclusive.
- Probe failure must **not** fail `eyes_open`. Still write the URL.
- Tests: fake HTTP (no live net in unit tests) for DENY, SAMEORIGIN, frame-ancestors none, no headers → ok, timeout → unknown.

## 7. Desktop pane

- Add `$cantEmbed` atom in `makeEngine()` (boolean, default false).
- `AgentEyesPane` must `useValue(engine.$cantEmbed)` so React re-renders.
- `pollOnce` must **not** blindly `clearCantEmbed()`. Clear only when `gaze.url` **changes**. If `gaze.embed === 'blocked'`, `setCantEmbed()` and **do not** set iframe `src`.
- `phaseForGaze`: if `gaze.embed === 'blocked'`, return `{ phase: 'error', code: 'cant-embed' }` so `ErrorState` shows even without the atom.
- Re-arm iframe load/error/timeout on every `src` change, not once at create. Treat `load` + inaccessible/blank document after timeout as cant-embed **only when embed is unknown**. If embed is `ok`, trust it. If `blocked`, never iframe.
- Slot background may stay dark; the error overlay must sit on top (`z-index`) so the user sees copy, not a black rectangle.
- Follow focused bot (`focusedSessionProfile ?? profile`) unchanged. `ctx.rest('/gaze')` first.

## 8. Fleet — add gork, split agent-eyes

`fleet.yaml`:

1. Add profile:
   ```yaml
   gork:
     home: ~/.hermes/profiles/gork
     role: >-
       Grok-Powered Generalist (profile gork). Lab-adjacent like jason, not
       company-facing. Gets Agent Eyes so the human can see what this bot is
       looking at. Does not get tiferet construction plugins.
   ```
2. Update header comments that say “three profiles” / “all three” to include gork where true. Do not add gork to tiferet-narrow packages or to `bot-kit-agent` as a whole (that would install `texting-style`).
3. Split the agent-eyes **agent-plugin** out of `bot-kit-agent` into its own package:

   ```yaml
   - name: agent-eyes
     source: hermes-bot-kit
     summary: Agent Eyes agent plugin — eyes_open/close + stills hook.
     profiles: [default, jason, gork]
     surfaces:
       - kind: agent-plugin
         from: agent-eyes/agent-plugin/agent-eyes
         install_as: agent-eyes
         enable: true
   ```

4. `bot-kit-agent` keeps `texting-style` + parked `orgo-computer` on `[default, jason]` only. Remove the agent-eyes surface from it.
5. `bot-kit-desktop` stays global with `from: agent-eyes` / `install_as: agent-eyes`. No change required unless comments still say “default+jason only”.
6. Materialize: `./fleet.cmd sync` then `./fleet.cmd sync --apply -k agent-eyes` then `./fleet.cmd enable agent-eyes --apply`. Confirm junction at `~/.hermes/profiles/gork/plugins/agent-eyes` → checkout tree. Confirm tiferet still has no agent-eyes dir.
7. Do not `hermes plugins enable` with `--allow-tool-override`.

## 9. Reload

Desktop Bot Chats are served by long-lived `hermes --profile <name> serve` processes. After code/symlink changes:

- Delete `__pycache__` under each installed `plugins/agent-eyes`.
- Kill that profile’s serve PID (it respawns on demand). Do not claim “works” from unit tests alone.

## 10. Out of scope

- Orgo hands, VNC, Playwright, `eyes_show`, tiferet, texting-style on gork, dumping lab plugins onto gork, migrating `hermes.plugin.computer-viewer.*`.
- Rewriting the desktop plugin from scratch. Patch the existing `plugin.js`.
- Hand-editing `config.yaml`.

## 11. Acceptance

1. `node --check hermes-bot-kit/agent-eyes/plugin.js` + ASCII-only byte scan pass.
2. `node --test hermes-bot-kit/agent-eyes/plugin.test.mjs` pass, including: `phaseForGaze({gaze:{url:'https://example.com', embed:'blocked'}})` → `cant-embed`; unsafe src never applied; 405 → `no-plugin`.
3. Agent tests (Python 3.12, `PYTHONPATH=agent-eyes`, `--import-mode=importlib`): dict-dispatch still green; `empty_gaze` includes `embed`; probe DENY → blocked; probe timeout → unknown; `eyes_open` dict payload returns `embed` matching the probe (mock HTTP).
4. `hermes plugins doctor <abs agent-plugin dir> --ci` passes.
5. `gork` has a live junction `plugins/agent-eyes` and `agent-eyes` remains in `plugins.enabled`. `tiferet` does not.
6. Smoke (no live desktop required for Grok, but must prove the data path):
   ```
   HERMES_HOME=~/.hermes/profiles/gork PYTHONPATH=... python -c "import tools; print(tools.eyes_open({'url':'https://example.com','title':'t'}))"
   ```
   JSON `ok: true`, `embed: blocked` (or `unknown` only if the probe truly could not see headers). `gaze.json` under gork’s cache matches.
7. Desktop: with `embed: blocked`, pane code path shows `cant-embed` ErrorState, iframe `src` not set. No black empty slot as the only UI.
8. `fleet status` lists `gork` and `agent-eyes` ok on default+jason+gork.
