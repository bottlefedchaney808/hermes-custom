/**
 * The built-in widgets.
 *
 * Every one of them answers a question that was previously unanswerable without
 * three `ls` commands and a good memory: what is installed where, what drifted,
 * what each profile costs, and which halves are global rather than per-profile.
 */

import { useState } from 'react'

import {
  ago,
  fmtBytes,
  getSignals,
  getState,
  type FleetState,
  type PackageRow,
  postSync,
  usePoll
} from './api'
import type { WidgetDef } from './registry'

// Verdict -> (glyph, class). The glyphs read at a glance in a dense table;
// the colours are semantic and deliberately do NOT follow the theme accent.
const MARK: Record<string, [string, string]> = {
  ok: ['●', 'm-ok'],
  create: ['○', 'm-warn'],
  relink: ['◑', 'm-warn'],
  convert: ['◑', 'm-warn'],
  refresh: ['◒', 'm-warn'],
  manual: ['◇', 'm-none'],
  missing: ['✕', 'm-bad']
}

function Mark({ verdict }: { verdict: string }) {
  const [glyph, cls] = MARK[verdict] ?? ['?', 'm-none']

  return (
    <span className={`fleet-cellmark ${cls}`} title={verdict}>
      {glyph}
    </span>
  )
}

function Pill({ verdict }: { verdict: string }) {
  return <span className={`fleet-pill v-${verdict}`}>{verdict}</span>
}

function Loading({ error, loading }: { error: null | string; loading: boolean }) {
  if (error) {
    return <span className="fleet-err">{error}</span>
  }

  return <span className="fleet-dim">{loading ? 'reading the fleet…' : 'no data'}</span>
}

/** Worst verdict among the actions a package has in one profile. Empty when the
 *  package does not target that profile at all — which is information, not a
 *  gap, so it renders as a dimmed dot rather than blank space. */
function cellVerdict(pkg: PackageRow, profile: string): null | string {
  const rows = pkg.actions.filter(a => a.profile === profile)

  if (rows.length === 0) {
    return null
  }
  const order = ['ok', 'manual', 'missing', 'refresh', 'convert', 'relink', 'create']

  return rows.map(r => r.verdict).sort((a, b) => order.indexOf(b) - order.indexOf(a))[0]
}

// ── the matrix ──────────────────────────────────────────────────────────────

function Matrix() {
  const { data, error, loading } = usePoll<FleetState>(() => getState(), 20_000)

  if (!data) {
    return <Loading error={error} loading={loading} />
  }

  const profiles = data.profiles.map(p => p.name)

  return (
    <table className="fleet-matrix">
      <thead>
        <tr>
          <th>package</th>
          {profiles.map(name => (
            <th key={name} style={{ textAlign: 'center' }}>
              {name}
            </th>
          ))}
          <th style={{ textAlign: 'center' }}>global</th>
        </tr>
      </thead>
      <tbody>
        {data.packages.map(pkg => {
          const globalRows = pkg.actions.filter(a => a.profile === null || a.profile === 'claude')

          return (
            <tr key={pkg.name} title={pkg.summary}>
              <td className="fleet-pkg">{pkg.name}</td>
              {profiles.map(name => {
                const verdict = cellVerdict(pkg, name)

                return (
                  <td className="cell" key={name}>
                    {verdict ? <Mark verdict={verdict} /> : <span className="fleet-cellmark m-none">·</span>}
                  </td>
                )
              })}
              <td className="cell">
                {globalRows.length > 0 ? (
                  <Mark verdict={globalRows.some(r => r.verdict !== 'ok') ? 'create' : 'ok'} />
                ) : (
                  <span className="fleet-cellmark m-none">·</span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ── drift + the sync console ────────────────────────────────────────────────

function Drift() {
  const { data, error, loading, refresh } = usePoll<FleetState>(() => getState(), 20_000)
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<null | string>(null)

  const run = (confirm: boolean) => {
    setBusy(true)
    setLog(confirm ? 'applying…' : 'planning…')
    postSync({ confirm })
      .then(result => {
        const verb = result.applied ? 'applied' : 'would change'

        setLog(`${verb} ${result.actions.length} surface(s)${result.errors.length ? ` · ${result.errors.length} error(s)` : ''}`)
        refresh()
      })
      .catch((err: unknown) => setLog(err instanceof Error ? err.message : String(err)))
      .finally(() => setBusy(false))
  }

  if (!data) {
    return <Loading error={error} loading={loading} />
  }

  const pending = data.packages.flatMap(p => p.actions.filter(a => !['ok', 'manual'].includes(a.verdict)))

  return (
    <>
      {pending.length === 0 ? (
        <div className="fleet-row">
          <span className="m-ok">in sync with fleet.yaml</span>
          <span className="fleet-dim">{data.packages.length} packages</span>
        </div>
      ) : (
        pending.slice(0, 40).map(action => (
          <div className="fleet-row" key={`${action.package}-${action.profile}-${action.target}`}>
            <span>
              <Pill verdict={action.verdict} /> <span className="fleet-pkg">{action.package}</span>{' '}
              <span className="fleet-dim">{action.profile ?? 'global'}</span>
            </span>
            <span className="fleet-dim">{action.kind}</span>
          </div>
        ))
      )}

      <div className="fleet-actions">
        <button className="fleet-btn" disabled={busy} onClick={() => run(false)} type="button">
          dry run
        </button>
        <button className="fleet-btn danger" disabled={busy || pending.length === 0} onClick={() => run(true)} type="button">
          apply
        </button>
        {log ? <span className="fleet-dim">{log}</span> : null}
      </div>
      <div className="fleet-note">
        Apply links packages into live agent homes. Dry run first — it is the same plan,
        without the writes.
      </div>
    </>
  )
}

// ── per-profile budget ──────────────────────────────────────────────────────

function Meter({ label, max, unit, value }: { label: string; max: number; unit?: string; value: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0

  return (
    <div className="fleet-meter">
      <span className="lbl">{label}</span>
      <span className="track">
        <span className="fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="val">
        {value}
        {unit ?? ''}
      </span>
    </div>
  )
}

function Budget() {
  const { data, error, loading } = usePoll<FleetState>(() => getState(), 30_000)

  if (!data) {
    return <Loading error={error} loading={loading} />
  }

  const maxPrompt = Math.max(...data.profiles.map(p => p.prompt_snapshot_bytes), 1)

  return (
    <>
      {data.profiles.map(profile => (
        <div key={profile.name} style={{ marginBottom: 8 }}>
          <div className="fleet-row">
            <span className="fleet-pkg">
              {profile.active ? '▸ ' : ''}
              {profile.name}
            </span>
            <span className="fleet-dim fleet-nums">
              {profile.skills} skills · {profile.plugins_installed} plugins · {profile.skins} skins
            </span>
          </div>
          <Meter
            label="prompt"
            max={maxPrompt}
            value={Math.round(profile.prompt_snapshot_bytes / 1024)}
            unit="K"
          />
        </div>
      ))}
      <div className="fleet-note">
        The prompt bar is the serialized skills prompt, rebuilt and paid on every turn.
        The gap between profiles is the tiering decision, made visible.
      </div>
    </>
  )
}

// ── what each package is, and why it is here ────────────────────────────────

function Packages() {
  const { data, error, loading } = usePoll<FleetState>(() => getState(), 60_000)
  const [open, setOpen] = useState<null | string>(null)

  if (!data) {
    return <Loading error={error} loading={loading} />
  }

  return (
    <>
      {data.packages.map(pkg => (
        <div key={pkg.name}>
          <div
            className="fleet-row"
            onClick={() => setOpen(open === pkg.name ? null : pkg.name)}
            style={{ cursor: 'pointer' }}
          >
            <span className="fleet-pkg">
              <Pill verdict={pkg.verdict} /> {pkg.name}
            </span>
            <span className="fleet-dim">{pkg.global ? 'global' : pkg.profiles.join(' ')}</span>
          </div>
          {open === pkg.name ? (
            <div className="fleet-note">
              {pkg.summary}
              {pkg.notes ? (
                <>
                  <br />
                  <br />
                  {pkg.notes}
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      ))}
    </>
  )
}

// ── the global half ─────────────────────────────────────────────────────────

function DesktopRoot() {
  const { data, error, loading } = usePoll<Record<string, Record<string, unknown>>>(() => getSignals(), 30_000)
  const desktop = data?.desktop as
    | undefined
    | { available: boolean; plugins?: Array<{ has_entry: boolean; name: string; unified: boolean }>; reason?: string }

  if (!desktop) {
    return <Loading error={error} loading={loading} />
  }
  if (!desktop.available) {
    return <span className="fleet-dim">{desktop.reason}</span>
  }

  return (
    <>
      {(desktop.plugins ?? []).map(plugin => (
        <div className="fleet-row" key={plugin.name}>
          <span className={plugin.has_entry ? 'fleet-pkg' : 'fleet-err'}>{plugin.name}</span>
          <span className="fleet-dim">{plugin.unified ? 'unified half' : 'standalone'}</span>
        </div>
      ))}
      <div className="fleet-note">
        One root for the whole app, never per profile — the desktop migrates any
        profile-scoped copy up here on purpose, so a pane cannot vanish when you
        switch agents.
      </div>
    </>
  )
}

// ── live signals ────────────────────────────────────────────────────────────

function Signals() {
  const { data, error, loading } = usePoll<Record<string, Record<string, unknown>>>(() => getSignals(), 30_000)

  if (!data) {
    return <Loading error={error} loading={loading} />
  }

  const rag = data.brain_rag as { available: boolean; bytes?: number; files?: number; reason?: string; updated_at?: number }
  const sessions = data.sessions as { available: boolean; counts?: Record<string, number> }

  return (
    <>
      <div className="fleet-row">
        <span>brain-rag index</span>
        <span className="fleet-dim fleet-nums">
          {rag?.available ? `${rag.files} files · ${fmtBytes(rag.bytes ?? 0)} · ${ago(rag.updated_at)}` : rag?.reason}
        </span>
      </div>
      {Object.entries(sessions?.counts ?? {}).map(([profile, count]) => (
        <div className="fleet-row" key={profile}>
          <span>sessions · {profile}</span>
          <span className="fleet-dim fleet-nums">{count}</span>
        </div>
      ))}
      {(['dynamic_workflows', 'token_optimizer'] as const).map(key => {
        const probe = data[key] as { available: boolean; entries?: number; reason?: string; updated_at?: number }

        return (
          <div className="fleet-row" key={key}>
            <span>{key.replace('_', '-')}</span>
            <span className="fleet-dim fleet-nums">
              {probe?.available ? `${probe.entries} entries · ${ago(probe.updated_at)}` : probe?.reason}
            </span>
          </div>
        )
      })}
    </>
  )
}

export const BUILTINS: WidgetDef[] = [
  {
    id: 'fleet.matrix',
    title: 'FLEET MATRIX',
    w: 7,
    h: 4,
    minW: 4,
    minH: 2,
    description: 'Every package against every profile, with live on-disk verdicts.',
    render: () => <Matrix />
  },
  {
    id: 'fleet.drift',
    title: 'DRIFT',
    w: 5,
    h: 4,
    minW: 3,
    minH: 2,
    description: 'Surfaces that no longer match fleet.yaml, and the button that fixes them.',
    render: () => <Drift />
  },
  {
    id: 'fleet.budget',
    title: 'PROFILE BUDGET',
    w: 4,
    h: 3,
    minW: 3,
    minH: 2,
    description: 'Skills, plugins, skins and the per-turn skills-prompt cost of each profile.',
    render: () => <Budget />
  },
  {
    id: 'fleet.packages',
    title: 'PACKAGES',
    w: 4,
    h: 3,
    minW: 3,
    minH: 2,
    description: 'What each package is and why it is installed where it is. Click a row.',
    render: () => <Packages />
  },
  {
    id: 'fleet.desktop',
    title: 'DESKTOP ROOT',
    w: 4,
    h: 3,
    minW: 3,
    minH: 2,
    description: 'The one global desktop-plugins root and what is materialized into it.',
    render: () => <DesktopRoot />
  },
  {
    id: 'fleet.signals',
    title: 'SIGNALS',
    w: 4,
    h: 3,
    minW: 3,
    minH: 2,
    description: 'Live per-package signals — index freshness, run counts, session volume.',
    render: () => <Signals />
  }
]

export const DEFAULT_BOARD = [
  'fleet.matrix',
  'fleet.drift',
  'fleet.budget',
  'fleet.packages',
  'fleet.signals'
]
