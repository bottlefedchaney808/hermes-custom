/**
 * The public widget registry.
 *
 * `hermes-home-dashboard` has a beautiful grid and a CLOSED catalog — its
 * widgets are internal to its bundle, there is no registry export and no window
 * hook, so nothing can add to it. That is the one thing this grid does
 * differently: the catalog is open, and registering into it is three lines from
 * any other desktop plugin.
 *
 *     const fleet = window.__HERMES_FLEET__
 *     fleet?.registerWidget({
 *       id: 'my-plugin.latency',
 *       title: 'LATENCY',
 *       w: 3, h: 2,
 *       render: () => React.createElement(MyLatency),
 *     })
 *
 * Registration is idempotent by id and may happen at any time — late arrivals
 * appear in the catalog without a reload, because the grid subscribes.
 */

import type { ReactNode } from 'react'

export interface WidgetDef {
  /** Unique, namespaced by convention: `<plugin>.<widget>`. Re-registering
   *  the same id replaces the previous definition. */
  id: string
  /** Shown in the widget header and in the catalog chip. Keep it short —
   *  the header is one line and clips. */
  title: string
  /** Default size in grid cells (12 columns wide overall). */
  w: number
  h: number
  /** Smallest the user may resize it to. Defaults to 2x1. */
  minW?: number
  minH?: number
  /** Longer description for the catalog tooltip. */
  description?: string
  /** The body. Rendered inside the widget chrome, below the header. */
  render: () => ReactNode
  /** Which plugin contributed it — stamped automatically for built-ins,
   *  useful for attribution in the catalog. */
  source?: string
}

type Listener = () => void

const widgets = new Map<string, WidgetDef>()
const listeners = new Set<Listener>()

function emit(): void {
  listeners.forEach(fn => {
    try {
      fn()
    } catch {
      // A broken subscriber must not stop the others from updating.
    }
  })
}

export function registerWidget(def: WidgetDef): () => void {
  if (!def?.id || typeof def.render !== 'function') {
    throw new Error('registerWidget: an id and a render function are required')
  }
  widgets.set(def.id, {
    minW: 2,
    minH: 1,
    source: 'external',
    ...def
  })
  emit()

  return () => {
    widgets.delete(def.id)
    emit()
  }
}

export function registerBuiltins(defs: WidgetDef[]): void {
  defs.forEach(def => widgets.set(def.id, { minW: 2, minH: 1, source: 'hermes-fleet', ...def }))
  emit()
}

export function listWidgets(): WidgetDef[] {
  return [...widgets.values()].sort((a, b) => a.title.localeCompare(b.title))
}

export function getWidget(id: string): undefined | WidgetDef {
  return widgets.get(id)
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn)

  return () => {
    listeners.delete(fn)
  }
}

/** Publish the registry on `window` so other plugins can find it without
 *  importing anything. Safe to call more than once. */
export function publish(version: string): void {
  if (typeof window === 'undefined') {
    return
  }
  ;(window as unknown as Record<string, unknown>).__HERMES_FLEET__ = {
    version,
    registerWidget,
    listWidgets,
    subscribe
  }
}
