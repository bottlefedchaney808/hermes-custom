/**
 * The grid engine — drag, resize, swap, trash, persist.
 *
 * Twelve columns, fixed row height, absolute placement. Items never overlap:
 * after every move the rest of the board reflows downward past whatever the
 * dragged box now occupies. Two boxes of identical size swap instead of
 * shoving, which is what makes rearranging a dense board feel deliberate
 * rather than like a fight.
 *
 * Layout lives in plugin-scoped storage (`hermes.plugin.hermes-fleet.layout`),
 * so it is per viewer and survives updates. Storage can throw or come back
 * empty — a wiped profile, a locked store — so every read is guarded and the
 * grid falls back to the default board rather than rendering nothing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getWidget, listWidgets, subscribe, type WidgetDef } from './registry'

export const COLS = 12
export const ROW_H = 78
export const GAP = 10

export interface Box {
  id: string
  widget: string
  gx: number
  gy: number
  gw: number
  gh: number
}

interface Store {
  get<T>(key: string, fallback: T): T
  set(key: string, value: unknown): void
}

function collide(a: Box, b: Box): boolean {
  return a.gx < b.gx + b.gw && a.gx + a.gw > b.gx && a.gy < b.gy + b.gh && a.gy + a.gh > b.gy
}

/** Push every box that the placed one now overlaps straight down, repeatedly,
 *  until the board is conflict-free. Returns only the rows that moved. */
function reflow(placedBox: Box, others: Box[]): Map<string, number> {
  const moved = new Map<string, number>()
  const rest = others.map(b => ({ ...b })).sort((a, b) => a.gy - b.gy)
  const settled: Box[] = [placedBox]

  for (const box of rest) {
    let guard = 0

    while (settled.some(p => collide(box, p)) && guard++ < 200) {
      const blocker = settled.find(p => collide(box, p))

      if (!blocker) {
        break
      }
      box.gy = blocker.gy + blocker.gh
    }
    settled.push(box)

    const original = others.find(o => o.id === box.id)

    if (original && box.gy !== original.gy) {
      moved.set(box.id, box.gy)
    }
  }

  return moved
}

/** A same-size box under the pointer is a swap target, not something to shove. */
function swapTarget(gx: number, gy: number, dragged: Box, others: Box[]): Box | undefined {
  return others.find(
    t =>
      t.id !== dragged.id &&
      t.gw === dragged.gw &&
      t.gh === dragged.gh &&
      gx >= t.gx &&
      gx < t.gx + t.gw &&
      gy >= t.gy &&
      gy < t.gy + t.gh
  )
}

/** First free slot that fits a w x h box, scanning top-left to bottom-right. */
function firstFit(boxes: Box[], w: number, h: number): { gx: number; gy: number } {
  for (let gy = 0; gy < 200; gy++) {
    for (let gx = 0; gx + w <= COLS; gx++) {
      const probe: Box = { id: '__probe', widget: '', gx, gy, gw: w, gh: h }

      if (!boxes.some(b => collide(probe, b))) {
        return { gx, gy }
      }
    }
  }

  return { gx: 0, gy: 0 }
}

function makeId(widget: string): string {
  return `${widget}#${Math.random().toString(36).slice(2, 8)}`
}

export function defaultBoard(ids: string[]): Box[] {
  const boxes: Box[] = []

  for (const widgetId of ids) {
    const def = getWidget(widgetId)

    if (!def) {
      continue
    }
    const at = firstFit(boxes, def.w, def.h)

    boxes.push({ id: makeId(widgetId), widget: widgetId, ...at, gw: def.w, gh: def.h })
  }

  return boxes
}

interface DragState {
  kind: 'move' | 'resize'
  id: string
  startX: number
  startY: number
  origin: Box
}

export function useWidgetCatalog(): WidgetDef[] {
  const [, bump] = useState(0)

  useEffect(() => subscribe(() => bump(n => n + 1)), [])

  return listWidgets()
}

interface GridProps {
  storage: Store
  storageKey: string
  initial: string[]
}

export function Grid({ storage, storageKey, initial }: GridProps) {
  const catalog = useWidgetCatalog()
  const stageRef = useRef<HTMLDivElement | null>(null)
  const [editing, setEditing] = useState(false)
  const [drag, setDrag] = useState<DragState | null>(null)
  const [ghost, setGhost] = useState<Box | null>(null)
  const [swapping, setSwapping] = useState<null | string>(null)

  const [boxes, setBoxes] = useState<Box[]>(() => {
    try {
      const saved = storage.get<Box[] | null>(storageKey, null)

      if (Array.isArray(saved) && saved.length > 0) {
        return saved
      }
    } catch {
      // Unreadable store — fall through to the default board.
    }

    return defaultBoard(initial)
  })

  const persist = useCallback(
    (next: Box[]) => {
      setBoxes(next)
      try {
        storage.set(storageKey, next)
      } catch {
        // Per-viewer convenience only; a failed write must never break the board.
      }
    },
    [storage, storageKey]
  )

  const cellW = useCallback(() => {
    const width = stageRef.current?.clientWidth ?? COLS * 100

    return (width - GAP * (COLS - 1)) / COLS
  }, [])

  const px = useCallback(
    (box: Box) => ({
      left: box.gx * (cellW() + GAP),
      top: box.gy * (ROW_H + GAP),
      width: box.gw * cellW() + (box.gw - 1) * GAP,
      height: box.gh * ROW_H + (box.gh - 1) * GAP
    }),
    [cellW]
  )

  // Pointer handling lives on the window so a fast drag that leaves the stage
  // still tracks — the same reason the host's own panes bind at window level.
  useEffect(() => {
    if (!drag) {
      return
    }

    const onMove = (event: PointerEvent) => {
      const unit = cellW() + GAP
      const dx = Math.round((event.clientX - drag.startX) / unit)
      const dy = Math.round((event.clientY - drag.startY) / (ROW_H + GAP))
      const others = boxes.filter(b => b.id !== drag.id)

      if (drag.kind === 'move') {
        const gx = Math.max(0, Math.min(COLS - drag.origin.gw, drag.origin.gx + dx))
        const gy = Math.max(0, drag.origin.gy + dy)
        const target = swapTarget(gx, gy, drag.origin, others)

        setSwapping(target?.id ?? null)
        setGhost(target ? { ...drag.origin, gx: target.gx, gy: target.gy } : { ...drag.origin, gx, gy })

        return
      }

      const def = getWidget(drag.origin.widget)
      const gw = Math.max(def?.minW ?? 2, Math.min(COLS - drag.origin.gx, drag.origin.gw + dx))
      const gh = Math.max(def?.minH ?? 1, drag.origin.gh + dy)

      setGhost({ ...drag.origin, gw, gh })
    }

    const onUp = () => {
      if (ghost) {
        const others = boxes.filter(b => b.id !== ghost.id)

        if (swapping) {
          const target = others.find(b => b.id === swapping)

          if (target) {
            persist(
              boxes.map(b => {
                if (b.id === ghost.id) {
                  return { ...b, gx: target.gx, gy: target.gy }
                }
                if (b.id === target.id) {
                  return { ...b, gx: drag.origin.gx, gy: drag.origin.gy }
                }

                return b
              })
            )
          }
        } else {
          const moved = reflow(ghost, others)

          persist(
            boxes.map(b => {
              if (b.id === ghost.id) {
                return ghost
              }
              const gy = moved.get(b.id)

              return gy === undefined ? b : { ...b, gy }
            })
          )
        }
      }
      setDrag(null)
      setGhost(null)
      setSwapping(null)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)

    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [drag, ghost, boxes, swapping, cellW, persist])

  const begin = (kind: DragState['kind'], box: Box) => (event: React.PointerEvent) => {
    if (!editing) {
      return
    }
    event.preventDefault()
    setDrag({ kind, id: box.id, startX: event.clientX, startY: event.clientY, origin: box })
    setGhost(box)
  }

  const add = (def: WidgetDef) => {
    const at = firstFit(boxes, def.w, def.h)

    persist([...boxes, { id: makeId(def.id), widget: def.id, ...at, gw: def.w, gh: def.h }])
  }

  const remove = (id: string) => persist(boxes.filter(b => b.id !== id))
  const reset = () => persist(defaultBoard(initial))

  const height = useMemo(
    () => Math.max(...boxes.map(b => b.gy + b.gh), 4) * (ROW_H + GAP),
    [boxes]
  )

  return (
    <div className={`fleet-root${editing ? ' editing' : ''}`}>
      <div className="fleet-stage" ref={stageRef} style={{ height }}>
        {ghost ? <div className={`fleet-ghost${swapping ? ' swap' : ''}`} style={px(ghost)} /> : null}

        {boxes.map(box => {
          const def = getWidget(box.widget)
          const dragging = drag?.id === box.id

          return (
            <div
              className={`fleet-widget${dragging ? ' dragging' : ''}${swapping === box.id ? ' swap-target' : ''}`}
              key={box.id}
              style={px(box)}
            >
              <span className="fleet-hd" onPointerDown={begin('move', box)}>
                {def?.title ?? box.widget}
              </span>

              {editing ? (
                <button aria-label="remove widget" className="fleet-x" onClick={() => remove(box.id)} type="button">
                  ×
                </button>
              ) : null}

              <div className="fleet-body">
                {def ? (
                  def.render()
                ) : (
                  <span className="fleet-err">
                    {box.widget} is not registered — the plugin that provided it may be disabled.
                  </span>
                )}
              </div>

              {editing ? <span className="fleet-rs" onPointerDown={begin('resize', box)} /> : null}
            </div>
          )
        })}
      </div>

      <div className={`fleet-catalog-wrap${editing ? ' open' : ''}`}>
        <div className="fleet-catalog">
          <div className="fleet-catalog-inner">
            <span className="fleet-catalog-hint">click to add</span>
            {catalog.map(def => (
              <button
                className="fleet-chip"
                key={def.id}
                onClick={() => add(def)}
                title={def.description ?? def.id}
                type="button"
              >
                {def.title}
                {def.source !== 'hermes-fleet' ? <em className="fleet-chip-src">{def.source}</em> : null}
              </button>
            ))}
            {catalog.length === 0 ? <span className="fleet-catalog-hint">no widgets registered</span> : null}
          </div>
        </div>
      </div>

      <div className="fleet-editbar">
        <button
          className={`fleet-fab${editing ? ' active' : ''}`}
          onClick={() => setEditing(v => !v)}
          title={editing ? 'done' : 'edit layout'}
          type="button"
        >
          {editing ? '✓' : '✎'}
        </button>
        {editing ? (
          <button className="fleet-fab" onClick={reset} title="restore the default board" type="button">
            ⟲
          </button>
        ) : null}
      </div>
    </div>
  )
}
