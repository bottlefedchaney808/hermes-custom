/**
 * hermes-fleet — the desktop half.
 *
 * Registers one route (`/fleet`), a sidebar entry, and a palette command. The
 * route renders an OPEN widget grid: the built-ins below, plus anything any
 * other plugin has registered through `window.__HERMES_FLEET__`.
 *
 * Plain ESM. The desktop plugin loader resolves exactly three specifiers —
 * `@hermes/plugin-sdk`, `react` and `react/jsx-runtime` — so everything else is
 * bundled in. Do not add a dependency expecting the loader to find it.
 */

import { host, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'

import { configure } from './api'
import { css } from './css'
import { Grid } from './grid'
import { publish, registerBuiltins } from './registry'
import { BUILTINS, DEFAULT_BOARD } from './widgets'

const ID = 'hermes-fleet'
const VERSION = '1.0.0'
const ROUTE = '/fleet'
const LAYOUT_KEY = 'layout.v1'

interface Storage {
  get<T>(key: string, fallback: T): T
  set(key: string, value: unknown): void
}

function FleetPage({ storage }: { storage: Storage }) {
  return (
    <>
      <style>{css}</style>
      <Grid initial={DEFAULT_BOARD} storage={storage} storageKey={LAYOUT_KEY} />
    </>
  )
}

export default {
  id: ID,
  name: 'Fleet',
  description:
    'Package x profile matrix, live drift against fleet.yaml, per-profile context budget — on an open widget grid other plugins can register into.',
  defaultEnabled: true,

  register(ctx: {
    register: (c: Record<string, unknown>) => () => void
    registerMany: (cs: Array<Record<string, unknown>>) => () => void
    rest: <T>(path: string, opts?: { body?: unknown; method?: string }) => Promise<T>
    storage: Storage
  }) {
    // One backend for both front ends. `ctx.rest` is namespaced to
    // /api/plugins/hermes-fleet by construction, so widgets cannot reach
    // another plugin's routes even by mistake.
    configure(ctx.rest)

    registerBuiltins(BUILTINS)
    publish(VERSION)

    ctx.registerMany([
      {
        id: 'route',
        area: ROUTES_AREA,
        title: 'Fleet',
        order: -900,
        data: { path: ROUTE },
        render: () => <FleetPage storage={ctx.storage} />
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: -900,
        data: { codicon: 'layers', label: 'Fleet', path: ROUTE }
      },
      {
        id: 'open',
        area: PALETTE_AREA,
        order: -900,
        data: {
          id: 'fleet.open',
          keywords: ['fleet', 'profiles', 'plugins', 'drift', 'install'],
          label: 'Open Fleet',
          run: () => host.navigate(ROUTE)
        }
      }
    ])
  }
}
