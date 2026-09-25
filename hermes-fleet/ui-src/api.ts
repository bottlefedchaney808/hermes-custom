/**
 * The one door to the backend, plus a polling hook.
 *
 * `ctx.rest` is namespaced to `/api/plugins/hermes-fleet` by construction, so
 * there is no way for a widget to reach another plugin's routes even by
 * accident. The context is captured once at register time and handed to the
 * widgets, which is why nothing here imports it globally.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface ActionRow {
  package: string
  kind: string
  profile: null | string
  source: null | string
  target: string
  verdict: string
  detail: string
  mode: string
  applied: null | string
}

export interface ProfileRow {
  name: string
  home: string
  role: string
  exists: boolean
  active: boolean
  plugins_installed: number
  plugins_enabled: string[]
  skills: number
  skins: number
  prompt_snapshot_bytes: number
  install_metadata: string[]
}

export interface PackageRow {
  name: string
  summary: string
  notes: string
  source: null | string
  upstream: null | string
  global: boolean
  profiles: string[]
  surfaces: string[]
  verdict: string
  actions: ActionRow[]
}

export interface FleetState {
  generated_at: string
  active_profile: string
  hermes_home: string
  desktop_root: string
  profiles: ProfileRow[]
  packages: PackageRow[]
  pending: number
  errors: string[]
  repo_discovered_by?: string
}

export interface Rest {
  <T>(path: string, opts?: { body?: unknown; method?: string }): Promise<T>
}

let rest: null | Rest = null

export function configure(fn: Rest): void {
  rest = fn
}

export function call<T>(path: string, opts?: { body?: unknown; method?: string }): Promise<T> {
  if (!rest) {
    return Promise.reject(new Error('hermes-fleet backend not configured'))
  }

  return rest<T>(path, opts)
}

export const getState = (force = false) => call<FleetState>(`/state${force ? '?force=true' : ''}`)
export const getSignals = () => call<Record<string, Record<string, unknown>>>('/signals')

export const postSync = (body: { confirm: boolean; package?: string; profile?: string }) =>
  call<{ actions: ActionRow[]; applied: boolean; errors: string[]; pending: number }>('/sync', {
    method: 'POST',
    body
  })

export const postToggle = (body: { confirm: boolean; on: boolean; package: string }) =>
  call<{ applied: boolean; next: string; results: Array<{ plugin: string; profile: string; result: string }> }>(
    '/toggle',
    { method: 'POST', body }
  )

export interface Poll<T> {
  data: null | T
  error: null | string
  loading: boolean
  refresh: (force?: boolean) => void
}

/**
 * Poll a backend route on an interval.
 *
 * Deliberately conservative: the default is 15s, not 1s. Every tick walks three
 * profile trees on disk, and a dashboard that hammers its own backend is how a
 * "monitoring" pane becomes the thing that needs monitoring. Widgets that want
 * faster can ask, but nothing here does by default.
 */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs = 15_000): Poll<T> {
  const [data, setData] = useState<null | T>(null)
  const [error, setError] = useState<null | string>(null)
  const [loading, setLoading] = useState(true)
  const alive = useRef(true)
  const run = useRef(fetcher)

  run.current = fetcher

  const refresh = useCallback(() => {
    setLoading(true)
    run
      .current()
      .then(value => {
        if (!alive.current) {
          return
        }
        setData(value)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!alive.current) {
          return
        }
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (alive.current) {
          setLoading(false)
        }
      })
  }, [])

  useEffect(() => {
    alive.current = true
    refresh()
    const timer = window.setInterval(refresh, intervalMs)

    return () => {
      alive.current = false
      window.clearInterval(timer)
    }
  }, [refresh, intervalMs])

  return { data, error, loading, refresh }
}

export function fmtBytes(bytes: number): string {
  if (!bytes) {
    return '—'
  }
  if (bytes < 1024) {
    return `${bytes}B`
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)}K`
  }

  return `${(bytes / 1024 / 1024).toFixed(1)}M`
}

export function ago(epochSeconds: null | number | undefined): string {
  if (!epochSeconds) {
    return '—'
  }
  const seconds = Date.now() / 1000 - epochSeconds

  if (seconds < 90) {
    return 'just now'
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)}m ago`
  }
  if (seconds < 86_400) {
    return `${Math.round(seconds / 3600)}h ago`
  }

  return `${Math.round(seconds / 86_400)}d ago`
}
