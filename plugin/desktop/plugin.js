// brain-rag desktop pane — search the Obsidian brain from the app.
// Loaded UNCOMPILED: jsx() calls only, no JSX syntax.
import { host } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const LEGS = ['all', 'Construction', 'Development', 'Trading']

function BrainRagPane(props) {
  const rest = props.rest
  const [query, setQuery] = useState('')
  const [leg, setLeg] = useState('all')
  const [hits, setHits] = useState([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')

  async function runSearch() {
    if (!query.trim()) return
    setBusy(true)
    setNote('')
    try {
      const result = await rest('/search', {
        method: 'POST',
        body: { query: query, leg: leg, k: 8 }
      })
      const found = (result && result.hits) || []
      setHits(found)
      if (found.length === 0) setNote('No hits in the brain.')
      else if (result.vector === 'skipped') setNote('Keyword only — embeddings unavailable.')
    } catch (err) {
      setHits([])
      setNote('brain-rag backend unavailable.')
    } finally {
      setBusy(false)
    }
  }

  const rows = hits.map(function (hit, i) {
    const where = hit.heading ? hit.path + ' § ' + hit.heading : hit.path
    return jsxs('div', {
      className: 'flex flex-col gap-1 border-b border-(--ui-stroke-secondary) py-2',
      children: [
        jsx('div', {
          className: 'text-[0.6875rem] text-(--ui-text-tertiary)',
          children: hit.leg + ' · ' + hit.date + ' · ' + where
        }),
        jsx('div', {
          className: 'text-xs text-(--ui-text-secondary)',
          children: String(hit.text || '').slice(0, 300)
        })
      ]
    }, hit.path + ':' + i)
  })

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 p-3 text-sm',
    children: [
      jsxs('div', {
        className: 'flex gap-2',
        children: [
          jsx('input', {
            className: 'flex-1 rounded border border-(--ui-stroke-secondary) px-2 py-1 text-xs',
            placeholder: 'search the brain',
            value: query,
            onChange: function (e) { setQuery(e.target.value) },
            onKeyDown: function (e) { if (e.key === 'Enter') void runSearch() }
          }),
          jsx('select', {
            className: 'rounded border border-(--ui-stroke-secondary) px-1 text-xs',
            value: leg,
            onChange: function (e) { setLeg(e.target.value) },
            children: LEGS.map(function (l) {
              return jsx('option', { value: l, children: l }, l)
            })
          })
        ]
      }),
      note
        ? jsx('div', { className: 'text-[0.6875rem] text-(--ui-text-quaternary)', children: note })
        : null,
      jsx('div', {
        className: 'flex-1 overflow-auto',
        children: busy
          ? jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'searching…' })
          : rows
      })
    ]
  })
}

export default {
  id: 'brain-rag',
  name: 'Brain RAG',
  register(ctx) {
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'brain',
      data: { placement: 'right', width: '320px' },
      render: function () { return jsx(BrainRagPane, { rest: ctx.rest }) }
    })
    ctx.register({
      id: 'reindex',
      area: 'palette',
      data: {
        title: 'Brain RAG: reindex vault',
        run: async function () {
          try {
            await ctx.rest('/index', { method: 'POST', body: { mode: 'incremental' } })
            host.notify({ kind: 'info', message: 'brain-rag reindexed' })
          } catch (err) {
            host.notify({ kind: 'error', message: 'brain-rag reindex failed' })
          }
        }
      }
    })
  }
}
