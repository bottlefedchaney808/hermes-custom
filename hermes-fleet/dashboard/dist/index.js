(() => {
  // ui-src/shims/react.ts
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK?.React) {
    throw new Error("hermes-fleet: window.__HERMES_PLUGIN_SDK__.React is missing \u2014 dashboard SDK not loaded");
  }
  var React = SDK.React;
  var hooks = SDK.hooks ?? {};
  var pick = (name) => hooks[name] ?? React[name];
  var useCallback = pick("useCallback");
  var useContext = pick("useContext");
  var useEffect = pick("useEffect");
  var useMemo = pick("useMemo");
  var useRef = pick("useRef");
  var useState = pick("useState");
  var createElement = React.createElement;
  var Fragment = React.Fragment;
  var react_default = React;

  // ui-src/api.ts
  var rest = null;
  function configure(fn) {
    rest = fn;
  }
  function call(path, opts) {
    if (!rest) {
      return Promise.reject(new Error("hermes-fleet backend not configured"));
    }
    return rest(path, opts);
  }
  var getState = (force = false) => call(`/state${force ? "?force=true" : ""}`);
  var getSignals = () => call("/signals");
  var postSync = (body) => call("/sync", {
    method: "POST",
    body
  });
  function usePoll(fetcher, intervalMs = 15e3) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const alive = useRef(true);
    const run = useRef(fetcher);
    run.current = fetcher;
    const refresh = useCallback(() => {
      setLoading(true);
      run.current().then((value) => {
        if (!alive.current) {
          return;
        }
        setData(value);
        setError(null);
      }).catch((err) => {
        if (!alive.current) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
      }).finally(() => {
        if (alive.current) {
          setLoading(false);
        }
      });
    }, []);
    useEffect(() => {
      alive.current = true;
      refresh();
      const timer = window.setInterval(refresh, intervalMs);
      return () => {
        alive.current = false;
        window.clearInterval(timer);
      };
    }, [refresh, intervalMs]);
    return { data, error, loading, refresh };
  }
  function fmtBytes(bytes) {
    if (!bytes) {
      return "\u2014";
    }
    if (bytes < 1024) {
      return `${bytes}B`;
    }
    if (bytes < 1024 * 1024) {
      return `${Math.round(bytes / 1024)}K`;
    }
    return `${(bytes / 1024 / 1024).toFixed(1)}M`;
  }
  function ago(epochSeconds) {
    if (!epochSeconds) {
      return "\u2014";
    }
    const seconds = Date.now() / 1e3 - epochSeconds;
    if (seconds < 90) {
      return "just now";
    }
    if (seconds < 3600) {
      return `${Math.round(seconds / 60)}m ago`;
    }
    if (seconds < 86400) {
      return `${Math.round(seconds / 3600)}h ago`;
    }
    return `${Math.round(seconds / 86400)}d ago`;
  }

  // ui-src/css.ts
  var css = `
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
.fleet-hd::before { content: "\u2500\u2500 "; opacity: 0.5; }
.fleet-hd::after { content: " \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"; opacity: 0.3; }
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

/* \u2500\u2500 catalog \u2500\u2500 */
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

/* \u2500\u2500 edit bar \u2500\u2500 */
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

/* \u2500\u2500 widget content primitives \u2500\u2500 */
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

/* \u2500\u2500 the matrix \u2500\u2500 */
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

/* \u2500\u2500 meters \u2500\u2500 */
.fleet-meter { display: flex; align-items: center; gap: 7px; margin: 3px 0; }
.fleet-meter .lbl { width: 54px; color: var(--color-muted-foreground, #7d8496); font-size: 10px; }
.fleet-meter .track { flex: 1; height: 7px; border-radius: 2px; background: rgb(255 255 255 / 0.07); overflow: hidden; }
.fleet-meter .fill {
  height: 100%; transition: width 0.6s ease;
  background: linear-gradient(90deg, var(--home-accent-dim), var(--home-accent));
}
.fleet-meter .val { width: 52px; text-align: right; font-size: 10px; font-variant-numeric: tabular-nums; }

/* \u2500\u2500 actions \u2500\u2500 */
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
`;

  // ui-src/registry.ts
  var widgets = /* @__PURE__ */ new Map();
  var listeners = /* @__PURE__ */ new Set();
  function emit() {
    listeners.forEach((fn) => {
      try {
        fn();
      } catch {
      }
    });
  }
  function registerWidget(def) {
    if (!def?.id || typeof def.render !== "function") {
      throw new Error("registerWidget: an id and a render function are required");
    }
    widgets.set(def.id, {
      minW: 2,
      minH: 1,
      source: "external",
      ...def
    });
    emit();
    return () => {
      widgets.delete(def.id);
      emit();
    };
  }
  function registerBuiltins(defs) {
    defs.forEach((def) => widgets.set(def.id, { minW: 2, minH: 1, source: "hermes-fleet", ...def }));
    emit();
  }
  function listWidgets() {
    return [...widgets.values()].sort((a, b) => a.title.localeCompare(b.title));
  }
  function getWidget(id) {
    return widgets.get(id);
  }
  function subscribe(fn) {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  }
  function publish(version) {
    if (typeof window === "undefined") {
      return;
    }
    ;
    window.__HERMES_FLEET__ = {
      version,
      registerWidget,
      listWidgets,
      subscribe
    };
  }

  // ui-src/shims/jsx-runtime.ts
  function create(type, props, key) {
    const { children, ...rest3 } = props ?? {};
    const args = [type, key === void 0 ? rest3 : { ...rest3, key }];
    if (Array.isArray(children)) {
      args.push(...children);
    } else if (children !== void 0) {
      args.push(children);
    }
    return react_default.createElement(...args);
  }
  var jsx = create;
  var jsxs = create;
  var Fragment2 = react_default.Fragment;

  // ui-src/grid.tsx
  var COLS = 12;
  var ROW_H = 78;
  var GAP = 10;
  function collide(a, b) {
    return a.gx < b.gx + b.gw && a.gx + a.gw > b.gx && a.gy < b.gy + b.gh && a.gy + a.gh > b.gy;
  }
  function reflow(placedBox, others) {
    const moved = /* @__PURE__ */ new Map();
    const rest3 = others.map((b) => ({ ...b })).sort((a, b) => a.gy - b.gy);
    const settled = [placedBox];
    for (const box of rest3) {
      let guard = 0;
      while (settled.some((p) => collide(box, p)) && guard++ < 200) {
        const blocker = settled.find((p) => collide(box, p));
        if (!blocker) {
          break;
        }
        box.gy = blocker.gy + blocker.gh;
      }
      settled.push(box);
      const original = others.find((o) => o.id === box.id);
      if (original && box.gy !== original.gy) {
        moved.set(box.id, box.gy);
      }
    }
    return moved;
  }
  function swapTarget(gx, gy, dragged, others) {
    return others.find(
      (t) => t.id !== dragged.id && t.gw === dragged.gw && t.gh === dragged.gh && gx >= t.gx && gx < t.gx + t.gw && gy >= t.gy && gy < t.gy + t.gh
    );
  }
  function firstFit(boxes, w, h) {
    for (let gy = 0; gy < 200; gy++) {
      for (let gx = 0; gx + w <= COLS; gx++) {
        const probe = { id: "__probe", widget: "", gx, gy, gw: w, gh: h };
        if (!boxes.some((b) => collide(probe, b))) {
          return { gx, gy };
        }
      }
    }
    return { gx: 0, gy: 0 };
  }
  function makeId(widget) {
    return `${widget}#${Math.random().toString(36).slice(2, 8)}`;
  }
  function defaultBoard(ids) {
    const boxes = [];
    for (const widgetId of ids) {
      const def = getWidget(widgetId);
      if (!def) {
        continue;
      }
      const at = firstFit(boxes, def.w, def.h);
      boxes.push({ id: makeId(widgetId), widget: widgetId, ...at, gw: def.w, gh: def.h });
    }
    return boxes;
  }
  function useWidgetCatalog() {
    const [, bump] = useState(0);
    useEffect(() => subscribe(() => bump((n) => n + 1)), []);
    return listWidgets();
  }
  function Grid({ storage: storage2, storageKey, initial }) {
    const catalog = useWidgetCatalog();
    const stageRef = useRef(null);
    const [editing, setEditing] = useState(false);
    const [drag, setDrag] = useState(null);
    const [ghost, setGhost] = useState(null);
    const [swapping, setSwapping] = useState(null);
    const [boxes, setBoxes] = useState(() => {
      try {
        const saved = storage2.get(storageKey, null);
        if (Array.isArray(saved) && saved.length > 0) {
          return saved;
        }
      } catch {
      }
      return defaultBoard(initial);
    });
    const persist = useCallback(
      (next) => {
        setBoxes(next);
        try {
          storage2.set(storageKey, next);
        } catch {
        }
      },
      [storage2, storageKey]
    );
    const cellW = useCallback(() => {
      const width = stageRef.current?.clientWidth ?? COLS * 100;
      return (width - GAP * (COLS - 1)) / COLS;
    }, []);
    const px = useCallback(
      (box) => ({
        left: box.gx * (cellW() + GAP),
        top: box.gy * (ROW_H + GAP),
        width: box.gw * cellW() + (box.gw - 1) * GAP,
        height: box.gh * ROW_H + (box.gh - 1) * GAP
      }),
      [cellW]
    );
    useEffect(() => {
      if (!drag) {
        return;
      }
      const onMove = (event) => {
        const unit = cellW() + GAP;
        const dx = Math.round((event.clientX - drag.startX) / unit);
        const dy = Math.round((event.clientY - drag.startY) / (ROW_H + GAP));
        const others = boxes.filter((b) => b.id !== drag.id);
        if (drag.kind === "move") {
          const gx = Math.max(0, Math.min(COLS - drag.origin.gw, drag.origin.gx + dx));
          const gy = Math.max(0, drag.origin.gy + dy);
          const target = swapTarget(gx, gy, drag.origin, others);
          setSwapping(target?.id ?? null);
          setGhost(target ? { ...drag.origin, gx: target.gx, gy: target.gy } : { ...drag.origin, gx, gy });
          return;
        }
        const def = getWidget(drag.origin.widget);
        const gw = Math.max(def?.minW ?? 2, Math.min(COLS - drag.origin.gx, drag.origin.gw + dx));
        const gh = Math.max(def?.minH ?? 1, drag.origin.gh + dy);
        setGhost({ ...drag.origin, gw, gh });
      };
      const onUp = () => {
        if (ghost) {
          const others = boxes.filter((b) => b.id !== ghost.id);
          if (swapping) {
            const target = others.find((b) => b.id === swapping);
            if (target) {
              persist(
                boxes.map((b) => {
                  if (b.id === ghost.id) {
                    return { ...b, gx: target.gx, gy: target.gy };
                  }
                  if (b.id === target.id) {
                    return { ...b, gx: drag.origin.gx, gy: drag.origin.gy };
                  }
                  return b;
                })
              );
            }
          } else {
            const moved = reflow(ghost, others);
            persist(
              boxes.map((b) => {
                if (b.id === ghost.id) {
                  return ghost;
                }
                const gy = moved.get(b.id);
                return gy === void 0 ? b : { ...b, gy };
              })
            );
          }
        }
        setDrag(null);
        setGhost(null);
        setSwapping(null);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      return () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
    }, [drag, ghost, boxes, swapping, cellW, persist]);
    const begin = (kind, box) => (event) => {
      if (!editing) {
        return;
      }
      event.preventDefault();
      setDrag({ kind, id: box.id, startX: event.clientX, startY: event.clientY, origin: box });
      setGhost(box);
    };
    const add = (def) => {
      const at = firstFit(boxes, def.w, def.h);
      persist([...boxes, { id: makeId(def.id), widget: def.id, ...at, gw: def.w, gh: def.h }]);
    };
    const remove = (id) => persist(boxes.filter((b) => b.id !== id));
    const reset = () => persist(defaultBoard(initial));
    const height = useMemo(
      () => Math.max(...boxes.map((b) => b.gy + b.gh), 4) * (ROW_H + GAP),
      [boxes]
    );
    return /* @__PURE__ */ jsxs("div", { className: `fleet-root${editing ? " editing" : ""}`, children: [
      /* @__PURE__ */ jsxs("div", { className: "fleet-stage", ref: stageRef, style: { height }, children: [
        ghost ? /* @__PURE__ */ jsx("div", { className: `fleet-ghost${swapping ? " swap" : ""}`, style: px(ghost) }) : null,
        boxes.map((box) => {
          const def = getWidget(box.widget);
          const dragging = drag?.id === box.id;
          return /* @__PURE__ */ jsxs(
            "div",
            {
              className: `fleet-widget${dragging ? " dragging" : ""}${swapping === box.id ? " swap-target" : ""}`,
              style: px(box),
              children: [
                /* @__PURE__ */ jsx("span", { className: "fleet-hd", onPointerDown: begin("move", box), children: def?.title ?? box.widget }),
                editing ? /* @__PURE__ */ jsx("button", { "aria-label": "remove widget", className: "fleet-x", onClick: () => remove(box.id), type: "button", children: "\xD7" }) : null,
                /* @__PURE__ */ jsx("div", { className: "fleet-body", children: def ? def.render() : /* @__PURE__ */ jsxs("span", { className: "fleet-err", children: [
                  box.widget,
                  " is not registered \u2014 the plugin that provided it may be disabled."
                ] }) }),
                editing ? /* @__PURE__ */ jsx("span", { className: "fleet-rs", onPointerDown: begin("resize", box) }) : null
              ]
            },
            box.id
          );
        })
      ] }),
      /* @__PURE__ */ jsx("div", { className: `fleet-catalog-wrap${editing ? " open" : ""}`, children: /* @__PURE__ */ jsx("div", { className: "fleet-catalog", children: /* @__PURE__ */ jsxs("div", { className: "fleet-catalog-inner", children: [
        /* @__PURE__ */ jsx("span", { className: "fleet-catalog-hint", children: "click to add" }),
        catalog.map((def) => /* @__PURE__ */ jsxs(
          "button",
          {
            className: "fleet-chip",
            onClick: () => add(def),
            title: def.description ?? def.id,
            type: "button",
            children: [
              def.title,
              def.source !== "hermes-fleet" ? /* @__PURE__ */ jsx("em", { className: "fleet-chip-src", children: def.source }) : null
            ]
          },
          def.id
        )),
        catalog.length === 0 ? /* @__PURE__ */ jsx("span", { className: "fleet-catalog-hint", children: "no widgets registered" }) : null
      ] }) }) }),
      /* @__PURE__ */ jsxs("div", { className: "fleet-editbar", children: [
        /* @__PURE__ */ jsx(
          "button",
          {
            className: `fleet-fab${editing ? " active" : ""}`,
            onClick: () => setEditing((v) => !v),
            title: editing ? "done" : "edit layout",
            type: "button",
            children: editing ? "\u2713" : "\u270E"
          }
        ),
        editing ? /* @__PURE__ */ jsx("button", { className: "fleet-fab", onClick: reset, title: "restore the default board", type: "button", children: "\u27F2" }) : null
      ] })
    ] });
  }

  // ui-src/widgets.tsx
  var MARK = {
    ok: ["\u25CF", "m-ok"],
    create: ["\u25CB", "m-warn"],
    relink: ["\u25D1", "m-warn"],
    convert: ["\u25D1", "m-warn"],
    refresh: ["\u25D2", "m-warn"],
    manual: ["\u25C7", "m-none"],
    missing: ["\u2715", "m-bad"]
  };
  function Mark({ verdict }) {
    const [glyph, cls] = MARK[verdict] ?? ["?", "m-none"];
    return /* @__PURE__ */ jsx("span", { className: `fleet-cellmark ${cls}`, title: verdict, children: glyph });
  }
  function Pill({ verdict }) {
    return /* @__PURE__ */ jsx("span", { className: `fleet-pill v-${verdict}`, children: verdict });
  }
  function Loading({ error, loading }) {
    if (error) {
      return /* @__PURE__ */ jsx("span", { className: "fleet-err", children: error });
    }
    return /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: loading ? "reading the fleet\u2026" : "no data" });
  }
  function cellVerdict(pkg, profile) {
    const rows = pkg.actions.filter((a) => a.profile === profile);
    if (rows.length === 0) {
      return null;
    }
    const order = ["ok", "manual", "missing", "refresh", "convert", "relink", "create"];
    return rows.map((r) => r.verdict).sort((a, b) => order.indexOf(b) - order.indexOf(a))[0];
  }
  function Matrix() {
    const { data, error, loading } = usePoll(() => getState(), 2e4);
    if (!data) {
      return /* @__PURE__ */ jsx(Loading, { error, loading });
    }
    const profiles = data.profiles.map((p) => p.name);
    return /* @__PURE__ */ jsxs("table", { className: "fleet-matrix", children: [
      /* @__PURE__ */ jsx("thead", { children: /* @__PURE__ */ jsxs("tr", { children: [
        /* @__PURE__ */ jsx("th", { children: "package" }),
        profiles.map((name) => /* @__PURE__ */ jsx("th", { style: { textAlign: "center" }, children: name }, name)),
        /* @__PURE__ */ jsx("th", { style: { textAlign: "center" }, children: "global" })
      ] }) }),
      /* @__PURE__ */ jsx("tbody", { children: data.packages.map((pkg) => {
        const globalRows = pkg.actions.filter((a) => a.profile === null || a.profile === "claude");
        return /* @__PURE__ */ jsxs("tr", { title: pkg.summary, children: [
          /* @__PURE__ */ jsx("td", { className: "fleet-pkg", children: pkg.name }),
          profiles.map((name) => {
            const verdict = cellVerdict(pkg, name);
            return /* @__PURE__ */ jsx("td", { className: "cell", children: verdict ? /* @__PURE__ */ jsx(Mark, { verdict }) : /* @__PURE__ */ jsx("span", { className: "fleet-cellmark m-none", children: "\xB7" }) }, name);
          }),
          /* @__PURE__ */ jsx("td", { className: "cell", children: globalRows.length > 0 ? /* @__PURE__ */ jsx(Mark, { verdict: globalRows.some((r) => r.verdict !== "ok") ? "create" : "ok" }) : /* @__PURE__ */ jsx("span", { className: "fleet-cellmark m-none", children: "\xB7" }) })
        ] }, pkg.name);
      }) })
    ] });
  }
  function Drift() {
    const { data, error, loading, refresh } = usePoll(() => getState(), 2e4);
    const [busy, setBusy] = useState(false);
    const [log, setLog] = useState(null);
    const run = (confirm) => {
      setBusy(true);
      setLog(confirm ? "applying\u2026" : "planning\u2026");
      postSync({ confirm }).then((result) => {
        const verb = result.applied ? "applied" : "would change";
        setLog(`${verb} ${result.actions.length} surface(s)${result.errors.length ? ` \xB7 ${result.errors.length} error(s)` : ""}`);
        refresh();
      }).catch((err) => setLog(err instanceof Error ? err.message : String(err))).finally(() => setBusy(false));
    };
    if (!data) {
      return /* @__PURE__ */ jsx(Loading, { error, loading });
    }
    const pending = data.packages.flatMap((p) => p.actions.filter((a) => !["ok", "manual"].includes(a.verdict)));
    return /* @__PURE__ */ jsxs(Fragment2, { children: [
      pending.length === 0 ? /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
        /* @__PURE__ */ jsx("span", { className: "m-ok", children: "in sync with fleet.yaml" }),
        /* @__PURE__ */ jsxs("span", { className: "fleet-dim", children: [
          data.packages.length,
          " packages"
        ] })
      ] }) : pending.slice(0, 40).map((action) => /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
        /* @__PURE__ */ jsxs("span", { children: [
          /* @__PURE__ */ jsx(Pill, { verdict: action.verdict }),
          " ",
          /* @__PURE__ */ jsx("span", { className: "fleet-pkg", children: action.package }),
          " ",
          /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: action.profile ?? "global" })
        ] }),
        /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: action.kind })
      ] }, `${action.package}-${action.profile}-${action.target}`)),
      /* @__PURE__ */ jsxs("div", { className: "fleet-actions", children: [
        /* @__PURE__ */ jsx("button", { className: "fleet-btn", disabled: busy, onClick: () => run(false), type: "button", children: "dry run" }),
        /* @__PURE__ */ jsx("button", { className: "fleet-btn danger", disabled: busy || pending.length === 0, onClick: () => run(true), type: "button", children: "apply" }),
        log ? /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: log }) : null
      ] }),
      /* @__PURE__ */ jsx("div", { className: "fleet-note", children: "Apply links packages into live agent homes. Dry run first \u2014 it is the same plan, without the writes." })
    ] });
  }
  function Meter({ label, max, unit, value }) {
    const pct = max > 0 ? Math.min(100, value / max * 100) : 0;
    return /* @__PURE__ */ jsxs("div", { className: "fleet-meter", children: [
      /* @__PURE__ */ jsx("span", { className: "lbl", children: label }),
      /* @__PURE__ */ jsx("span", { className: "track", children: /* @__PURE__ */ jsx("span", { className: "fill", style: { width: `${pct}%` } }) }),
      /* @__PURE__ */ jsxs("span", { className: "val", children: [
        value,
        unit ?? ""
      ] })
    ] });
  }
  function Budget() {
    const { data, error, loading } = usePoll(() => getState(), 3e4);
    if (!data) {
      return /* @__PURE__ */ jsx(Loading, { error, loading });
    }
    const maxPrompt = Math.max(...data.profiles.map((p) => p.prompt_snapshot_bytes), 1);
    return /* @__PURE__ */ jsxs(Fragment2, { children: [
      data.profiles.map((profile) => /* @__PURE__ */ jsxs("div", { style: { marginBottom: 8 }, children: [
        /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
          /* @__PURE__ */ jsxs("span", { className: "fleet-pkg", children: [
            profile.active ? "\u25B8 " : "",
            profile.name
          ] }),
          /* @__PURE__ */ jsxs("span", { className: "fleet-dim fleet-nums", children: [
            profile.skills,
            " skills \xB7 ",
            profile.plugins_installed,
            " plugins \xB7 ",
            profile.skins,
            " skins"
          ] })
        ] }),
        /* @__PURE__ */ jsx(
          Meter,
          {
            label: "prompt",
            max: maxPrompt,
            value: Math.round(profile.prompt_snapshot_bytes / 1024),
            unit: "K"
          }
        )
      ] }, profile.name)),
      /* @__PURE__ */ jsx("div", { className: "fleet-note", children: "The prompt bar is the serialized skills prompt, rebuilt and paid on every turn. The gap between profiles is the tiering decision, made visible." })
    ] });
  }
  function Packages() {
    const { data, error, loading } = usePoll(() => getState(), 6e4);
    const [open, setOpen] = useState(null);
    if (!data) {
      return /* @__PURE__ */ jsx(Loading, { error, loading });
    }
    return /* @__PURE__ */ jsx(Fragment2, { children: data.packages.map((pkg) => /* @__PURE__ */ jsxs("div", { children: [
      /* @__PURE__ */ jsxs(
        "div",
        {
          className: "fleet-row",
          onClick: () => setOpen(open === pkg.name ? null : pkg.name),
          style: { cursor: "pointer" },
          children: [
            /* @__PURE__ */ jsxs("span", { className: "fleet-pkg", children: [
              /* @__PURE__ */ jsx(Pill, { verdict: pkg.verdict }),
              " ",
              pkg.name
            ] }),
            /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: pkg.global ? "global" : pkg.profiles.join(" ") })
          ]
        }
      ),
      open === pkg.name ? /* @__PURE__ */ jsxs("div", { className: "fleet-note", children: [
        pkg.summary,
        pkg.notes ? /* @__PURE__ */ jsxs(Fragment2, { children: [
          /* @__PURE__ */ jsx("br", {}),
          /* @__PURE__ */ jsx("br", {}),
          pkg.notes
        ] }) : null
      ] }) : null
    ] }, pkg.name)) });
  }
  function DesktopRoot() {
    const { data, error, loading } = usePoll(() => getSignals(), 3e4);
    const desktop = data?.desktop;
    if (!desktop) {
      return /* @__PURE__ */ jsx(Loading, { error, loading });
    }
    if (!desktop.available) {
      return /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: desktop.reason });
    }
    return /* @__PURE__ */ jsxs(Fragment2, { children: [
      (desktop.plugins ?? []).map((plugin) => /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
        /* @__PURE__ */ jsx("span", { className: plugin.has_entry ? "fleet-pkg" : "fleet-err", children: plugin.name }),
        /* @__PURE__ */ jsx("span", { className: "fleet-dim", children: plugin.unified ? "unified half" : "standalone" })
      ] }, plugin.name)),
      /* @__PURE__ */ jsx("div", { className: "fleet-note", children: "One root for the whole app, never per profile \u2014 the desktop migrates any profile-scoped copy up here on purpose, so a pane cannot vanish when you switch agents." })
    ] });
  }
  function Signals() {
    const { data, error, loading } = usePoll(() => getSignals(), 3e4);
    if (!data) {
      return /* @__PURE__ */ jsx(Loading, { error, loading });
    }
    const rag = data.brain_rag;
    const sessions = data.sessions;
    return /* @__PURE__ */ jsxs(Fragment2, { children: [
      /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
        /* @__PURE__ */ jsx("span", { children: "brain-rag index" }),
        /* @__PURE__ */ jsx("span", { className: "fleet-dim fleet-nums", children: rag?.available ? `${rag.files} files \xB7 ${fmtBytes(rag.bytes ?? 0)} \xB7 ${ago(rag.updated_at)}` : rag?.reason })
      ] }),
      Object.entries(sessions?.counts ?? {}).map(([profile, count]) => /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
        /* @__PURE__ */ jsxs("span", { children: [
          "sessions \xB7 ",
          profile
        ] }),
        /* @__PURE__ */ jsx("span", { className: "fleet-dim fleet-nums", children: count })
      ] }, profile)),
      ["dynamic_workflows", "token_optimizer"].map((key) => {
        const probe = data[key];
        return /* @__PURE__ */ jsxs("div", { className: "fleet-row", children: [
          /* @__PURE__ */ jsx("span", { children: key.replace("_", "-") }),
          /* @__PURE__ */ jsx("span", { className: "fleet-dim fleet-nums", children: probe?.available ? `${probe.entries} entries \xB7 ${ago(probe.updated_at)}` : probe?.reason })
        ] }, key);
      })
    ] });
  }
  var BUILTINS = [
    {
      id: "fleet.matrix",
      title: "FLEET MATRIX",
      w: 7,
      h: 4,
      minW: 4,
      minH: 2,
      description: "Every package against every profile, with live on-disk verdicts.",
      render: () => /* @__PURE__ */ jsx(Matrix, {})
    },
    {
      id: "fleet.drift",
      title: "DRIFT",
      w: 5,
      h: 4,
      minW: 3,
      minH: 2,
      description: "Surfaces that no longer match fleet.yaml, and the button that fixes them.",
      render: () => /* @__PURE__ */ jsx(Drift, {})
    },
    {
      id: "fleet.budget",
      title: "PROFILE BUDGET",
      w: 4,
      h: 3,
      minW: 3,
      minH: 2,
      description: "Skills, plugins, skins and the per-turn skills-prompt cost of each profile.",
      render: () => /* @__PURE__ */ jsx(Budget, {})
    },
    {
      id: "fleet.packages",
      title: "PACKAGES",
      w: 4,
      h: 3,
      minW: 3,
      minH: 2,
      description: "What each package is and why it is installed where it is. Click a row.",
      render: () => /* @__PURE__ */ jsx(Packages, {})
    },
    {
      id: "fleet.desktop",
      title: "DESKTOP ROOT",
      w: 4,
      h: 3,
      minW: 3,
      minH: 2,
      description: "The one global desktop-plugins root and what is materialized into it.",
      render: () => /* @__PURE__ */ jsx(DesktopRoot, {})
    },
    {
      id: "fleet.signals",
      title: "SIGNALS",
      w: 4,
      h: 3,
      minW: 3,
      minH: 2,
      description: "Live per-package signals \u2014 index freshness, run counts, session volume.",
      render: () => /* @__PURE__ */ jsx(Signals, {})
    }
  ];
  var DEFAULT_BOARD = [
    "fleet.matrix",
    "fleet.drift",
    "fleet.budget",
    "fleet.packages",
    "fleet.signals"
  ];

  // ui-src/dashboard.tsx
  var ID = "hermes-fleet";
  var VERSION = "1.0.0";
  var PREFIX = `/api/plugins/${ID}`;
  var LAYOUT_KEY = `hermes.plugin.${ID}.layout.v1`;
  var SDK2 = window.__HERMES_PLUGIN_SDK__;
  var PLUGINS = window.__HERMES_PLUGINS__;
  function rest2(path, opts) {
    if (!SDK2) {
      return Promise.reject(new Error("dashboard SDK not available"));
    }
    const init = { method: opts?.method ?? "GET" };
    if (opts?.body !== void 0) {
      init.body = JSON.stringify(opts.body);
      init.headers = { "Content-Type": "application/json" };
    }
    return SDK2.fetchJSON(`${PREFIX}${path}`, init);
  }
  var storage = {
    get(key, fallback) {
      try {
        const raw = window.localStorage.getItem(`${LAYOUT_KEY}.${key}`);
        return raw === null ? fallback : JSON.parse(raw);
      } catch {
        return fallback;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(`${LAYOUT_KEY}.${key}`, JSON.stringify(value));
      } catch {
      }
    }
  };
  function FleetPage() {
    return /* @__PURE__ */ jsxs(Fragment2, { children: [
      /* @__PURE__ */ jsx("style", { children: css }),
      /* @__PURE__ */ jsx(Grid, { initial: DEFAULT_BOARD, storage, storageKey: "board" })
    ] });
  }
  configure(rest2);
  registerBuiltins(BUILTINS);
  publish(VERSION);
  if (PLUGINS) {
    PLUGINS.register(ID, FleetPage);
  } else {
    console.warn("[hermes-fleet] window.__HERMES_PLUGINS__ missing \u2014 dashboard tab will not mount");
  }
})();
