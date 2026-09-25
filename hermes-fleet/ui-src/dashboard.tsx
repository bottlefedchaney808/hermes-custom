/**
 * hermes-fleet — the web dashboard half.
 *
 * Same widgets, same backend, different host. The dashboard hands plugins its
 * React instance and a `fetchJSON` on `window.__HERMES_PLUGIN_SDK__` instead of
 * resolving module specifiers, so this entry adapts those two things and then
 * mounts exactly the grid the desktop mounts.
 *
 * Built as an IIFE (the dashboard loads a plain script, not an ES module) with
 * `react` and `react/jsx-runtime` aliased to the shims in ./shims.
 */

import { configure } from './api'
import { css } from './css'
import { Grid } from './grid'
import { publish, registerBuiltins } from './registry'
import { BUILTINS, DEFAULT_BOARD } from './widgets'

const ID = 'hermes-fleet'
const VERSION = '1.0.0'
const PREFIX = `/api/plugins/${ID}`
const LAYOUT_KEY = `hermes.plugin.${ID}.layout.v1`

interface DashboardSdk {
  fetchJSON: <T>(url: string, init?: RequestInit) => Promise<T>
}

const SDK = (window as unknown as { __HERMES_PLUGIN_SDK__?: DashboardSdk }).__HERMES_PLUGIN_SDK__
const PLUGINS = (window as unknown as { __HERMES_PLUGINS__?: { register: (id: string, c: unknown) => void } })
  .__HERMES_PLUGINS__

/** `ctx.rest`-shaped door over the dashboard's `fetchJSON`, pinned to this
 *  plugin's own namespace so the two hosts behave identically. */
function rest<T>(path: string, opts?: { body?: unknown; method?: string }): Promise<T> {
  if (!SDK) {
    return Promise.reject(new Error('dashboard SDK not available'))
  }
  const init: RequestInit = { method: opts?.method ?? 'GET' }

  if (opts?.body !== undefined) {
    init.body = JSON.stringify(opts.body)
    init.headers = { 'Content-Type': 'application/json' }
  }

  return SDK.fetchJSON<T>(`${PREFIX}${path}`, init)
}

/**
 * The desktop gives plugins namespaced `ctx.storage`; the dashboard does not,
 * so we build the same shape over localStorage under the same key prefix.
 * Every access is guarded — a private window, cleared site data or a blocked
 * store makes these throw, and a layout preference is never worth a blank page.
 */
const storage = {
  get<T>(key: string, fallback: T): T {
    try {
      const raw = window.localStorage.getItem(`${LAYOUT_KEY}.${key}`)

      return raw === null ? fallback : (JSON.parse(raw) as T)
    } catch {
      return fallback
    }
  },
  set(key: string, value: unknown): void {
    try {
      window.localStorage.setItem(`${LAYOUT_KEY}.${key}`, JSON.stringify(value))
    } catch {
      // Per-viewer convenience only.
    }
  }
}

function FleetPage() {
  return (
    <>
      <style>{css}</style>
      <Grid initial={DEFAULT_BOARD} storage={storage} storageKey="board" />
    </>
  )
}

configure(rest)
registerBuiltins(BUILTINS)
publish(VERSION)

if (PLUGINS) {
  PLUGINS.register(ID, FleetPage)
} else {
  console.warn('[hermes-fleet] window.__HERMES_PLUGINS__ missing — dashboard tab will not mount')
}
