/**
 * Styles, deliberately matched to `hermes-home-dashboard`.
 *
 * Everything routes through `--home-accent` (the active theme's primary), so
 * switching themes recolors the whole pane with zero widget changes — the same
 * trick Home uses, and the reason the two panes look like one product instead
 * of two plugins that happen to be installed together. Verdict colours are the
 * exception: they are semantics, not theme, and must not drift with the accent.
 */

export const css = `
.fleet-root {
  --home-accent: var(--color-primary, var(--ui-accent, #ffd700));
  --home-accent-dim: color-mix(in srgb, var(--home-accent) 55%, #000);
  --home-surface: color-mix(in srgb, var(--home-accent) 6%, var(--ui-editor-surface-background, rgb(10 10 14 / 0.55)));
  --home-border: color-mix(in srgb, var(--home-accent) 18%, transparent);
  --fleet-ok: #3fb950;
  --fleet-warn: #f5b945;
  --fleet-bad: #e25555;
  --fleet-new: #2dd4bf;
  position: relative;
  height: 100%;
  overflow: auto;
  padding: 14px 12px 0;
  font-family: var(--theme-font-mono, ui-monospace, monospace);
  font-size: 11px;
  line-height: 1.5;
  color: var(--color-foreground, var(--ui-text-primary, #d8dce6));
}

.fleet-stage { position: relative; min-height: 50vh; touch-action: none; }

.fleet-widget {
  position: absolute;
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--home-surface);
  border: 1px solid var(--home-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: 0 10px 30px rgb(0 0 0 / 0.5);
  overflow: hidden;
  transition: left 0.18s ease, top 0.18s ease, width 0.18s ease, height 0.18s ease;
  container-type: size;
  /* Own compositor layer: without it, one repainting widget forces its
     neighbours' backdrop-filter to recompose and the whole board flickers. */
  transform: translateZ(0);
  contain: paint;
}
.fleet-root.editing .fleet-widget { user-select: none; }
.fleet-widget.dragging { transition: none; opacity: 0.9; border-color: var(--home-accent); z-index: 50; }
.fleet-widget.swap-target {
  border-color: var(--fleet-new);
  box-shadow: 0 0 0 1px rgb(45 212 191 / 0.5), 0 10px 30px rgb(0 0 0 / 0.5);
}

.fleet-hd {
  display: block;
  font-size: 9px;
  letter-spacing: 0.18em;
  margin-bottom: 6px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--home-accent-dim);
  white-space: nowrap;
  overflow: hidden;
}
.fleet-hd::before { content: "── "; opacity: 0.5; }
.fleet-hd::after { content: " ─────────────────────────────────"; opacity: 0.3; }
.fleet-root.editing .fleet-hd { cursor: grab; }
.fleet-widget.dragging .fleet-hd { cursor: grabbing; }

.fleet-body { height: calc(100% - 20px); overflow: auto; }
.fleet-err { color: var(--fleet-bad); }

.fleet-x {
  position: absolute; top: 4px; right: 6px; z-index: 3;
  background: none; border: none; color: var(--fleet-bad);
  font-size: 13px; line-height: 1; cursor: pointer; padding: 2px 4px;
}
.fleet-rs {
  position: absolute; right: 2px; bottom: 2px; width: 13px; height: 13px;
  cursor: nwse-resize; border-radius: 2px; z-index: 3;
  border-right: 2px solid color-mix(in srgb, var(--home-accent) 45%, transparent);
  border-bottom: 2px solid color-mix(in srgb, var(--home-accent) 45%, transparent);
}

.fleet-ghost {
  position: absolute; z-index: 5; display: block; pointer-events: none;
  border: 1.5px dashed color-mix(in srgb, var(--home-accent) 70%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--home-accent) 7%, transparent);
  transition: left 0.18s ease, top 0.18s ease, width 0.18s ease, height 0.18s ease;
}
.fleet-ghost.swap { border-color: rgb(45 212 191 / 0.85); background: rgb(45 212 191 / 0.08); }

/* ── catalog ── */
.fleet-catalog-wrap {
  display: grid; grid-template-rows: 0fr; margin: 0;
  opacity: 0; pointer-events: none;
  transition: grid-template-rows 0.34s cubic-bezier(0.34, 1.2, 0.64, 1), opacity 0.28s ease, margin-top 0.34s ease;
}
.fleet-catalog-wrap.open { grid-template-rows: 1fr; opacity: 1; pointer-events: auto; margin-top: 10px; }
.fleet-catalog {
  overflow: hidden; min-height: 0; border-radius: 8px;
  background: var(--home-surface); border: 1px solid var(--home-border);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
}
.fleet-catalog-inner { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px; }
.fleet-catalog-hint { font-size: 10px; color: var(--color-muted-foreground, #6b7387); margin-right: 4px; }
.fleet-chip {
  font-family: inherit; font-size: 11px; padding: 4px 10px; border-radius: 6px; cursor: pointer;
  background: none; border: 1px dashed var(--home-border); color: var(--color-foreground, #d8dce6);
  transition: border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}
.fleet-chip:hover { border-color: var(--home-accent); color: var(--home-accent); transform: translateY(-1px); }
.fleet-chip:active { transform: scale(0.95); }
.fleet-chip-src { font-style: normal; opacity: 0.5; margin-left: 6px; font-size: 9px; }

/* ── edit bar ── */
.fleet-editbar { display: flex; justify-content: center; gap: 10px; padding: 18px 12px 26px; }
.fleet-fab {
  width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 14px; cursor: pointer; color: var(--home-accent);
  background: var(--home-surface); border: 1px solid var(--home-border);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  transition: border-color 0.25s ease, background 0.35s ease, transform 0.4s cubic-bezier(0.34, 1.4, 0.64, 1);
}
.fleet-fab:hover { border-color: var(--home-accent); transform: scale(1.06); }
.fleet-fab:active { transform: scale(0.94); }
.fleet-fab.active { background: color-mix(in srgb, var(--home-accent) 22%, transparent); }

/* ── widget content primitives ── */
.fleet-row {
  display: flex; justify-content: space-between; gap: 8px; padding: 1px 0;
  border-bottom: 1px solid rgb(255 255 255 / 0.04);
}
.fleet-row:last-child { border-bottom: none; }
.fleet-dim { color: var(--color-muted-foreground, #6b7387); }
.fleet-big { font-size: min(9cqw, 22cqh); font-weight: 700; color: var(--home-accent); }
.fleet-nums { font-variant-numeric: tabular-nums; }

.fleet-pill {
  display: inline-block; padding: 0 5px; border-radius: 4px; font-size: 9px;
  letter-spacing: 0.06em; text-transform: uppercase; font-weight: 700;
}
.v-ok      { color: var(--fleet-ok);   background: color-mix(in srgb, var(--fleet-ok) 14%, transparent); }
.v-create  { color: var(--fleet-new);  background: color-mix(in srgb, var(--fleet-new) 14%, transparent); }
.v-relink,
.v-convert,
.v-refresh { color: var(--fleet-warn); background: color-mix(in srgb, var(--fleet-warn) 14%, transparent); }
.v-missing { color: var(--fleet-bad);  background: color-mix(in srgb, var(--fleet-bad) 14%, transparent); }
.v-manual  { color: var(--color-muted-foreground, #6b7387); background: rgb(255 255 255 / 0.05); }

/* ── the matrix ── */
.fleet-matrix { width: 100%; border-collapse: collapse; font-size: 10px; }
.fleet-matrix th {
  text-align: left; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--home-accent-dim); padding: 2px 6px 4px 0; font-size: 9px;
  position: sticky; top: 0; background: var(--home-surface);
}
.fleet-matrix td { padding: 2px 6px 2px 0; border-bottom: 1px solid rgb(255 255 255 / 0.04); }
.fleet-matrix td.cell { text-align: center; width: 54px; }
.fleet-matrix tr:hover td { background: rgb(255 255 255 / 0.03); }
.fleet-pkg { color: var(--color-foreground, #d8dce6); white-space: nowrap; }
.fleet-cellmark { font-size: 12px; line-height: 1; }
.m-ok { color: var(--fleet-ok); }
.m-warn { color: var(--fleet-warn); }
.m-bad { color: var(--fleet-bad); }
.m-none { color: rgb(255 255 255 / 0.13); }

/* ── meters ── */
.fleet-meter { display: flex; align-items: center; gap: 7px; margin: 3px 0; }
.fleet-meter .lbl { width: 54px; color: var(--color-muted-foreground, #7d8496); font-size: 10px; }
.fleet-meter .track { flex: 1; height: 7px; border-radius: 2px; background: rgb(255 255 255 / 0.07); overflow: hidden; }
.fleet-meter .fill {
  height: 100%; transition: width 0.6s ease;
  background: linear-gradient(90deg, var(--home-accent-dim), var(--home-accent));
}
.fleet-meter .val { width: 52px; text-align: right; font-size: 10px; font-variant-numeric: tabular-nums; }

/* ── actions ── */
.fleet-btn {
  font-family: inherit; font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 10px; border-radius: 6px; cursor: pointer;
  background: none; border: 1px solid var(--home-border); color: var(--home-accent);
  transition: border-color 0.2s ease, background 0.2s ease;
}
.fleet-btn:hover:not(:disabled) { border-color: var(--home-accent); background: color-mix(in srgb, var(--home-accent) 10%, transparent); }
.fleet-btn:disabled { opacity: 0.4; cursor: default; }
.fleet-btn.danger { color: var(--fleet-warn); }
.fleet-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-top: 6px; }

.fleet-note { color: var(--color-muted-foreground, #6b7387); font-size: 10px; margin-top: 4px; }
.fleet-mono { font-family: inherit; word-break: break-all; }

@media (prefers-reduced-motion: reduce) {
  .fleet-widget, .fleet-ghost, .fleet-fab, .fleet-catalog-wrap { transition: none; }
}
`
