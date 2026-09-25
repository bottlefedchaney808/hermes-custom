// brain-rag desktop pane — search the Obsidian brain from the app,
// with the vault-graph board embedded (graph-only, no white chrome).
// Loaded UNCOMPILED: jsx() calls only, no JSX syntax.
import { host } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const LEGS = ['all', 'Construction', 'Development', 'Trading']
const GRAPH_PATH = 'C:/Users/bottl/hermes-artifacts/artifacts/vault-graph/index.html'

function fileUrlFromPath(p) {
  var s = String(p || '').replace(/\\/g, '/')
  if (s.indexOf('file:') === 0) return s
  if (s.charAt(0) !== '/') s = '/' + s
  return 'file://' + s
}

function graphSrc() {
  return fileUrlFromPath(GRAPH_PATH) + '?embed=1'
}

function GraphFrame() {
  var url = graphSrc()
  var webviewOk = typeof window !== 'undefined' && typeof window.HTMLWebViewElement !== 'undefined'
  if (webviewOk) {
    return jsx('webview', {
      src: url,
      partition: 'persist:brain-rag',
      allowpopups: 'true',
      style: { width: '100%', height: '100%', border: 0, display: 'flex', flex: 1 }
    })
  }
  return jsx('iframe', {
    src: url,
    title: 'brain-graph',
    className: 'h-full w-full border-0',
    sandbox: 'allow-scripts allow-same-origin'
  })
}

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
    const loc = hit.heading || hit.session_id
    const where = loc ? hit.path + ' § ' + loc : hit.path
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

  const hitPanel = (hits.length || note || busy)
    ? jsxs('div', {
        className: 'pointer-events-auto max-h-[40%] overflow-auto border-t border-(--ui-stroke-secondary) bg-(--ui-bg-primary) p-2',
        children: [
          note
            ? jsx('div', { className: 'text-[0.6875rem] text-(--ui-text-quaternary)', children: note })
            : null,
          busy
            ? jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'searching…' })
            : rows
        ]
      })
    : null

  return jsxs('div', {
    className: 'relative flex h-full min-h-0 flex-col text-sm',
    children: [
      jsxs('div', {
        className: 'z-10 flex shrink-0 gap-2 p-2',
        children: [
          jsx('input', {
            className: 'flex-1 rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1 text-xs',
            placeholder: 'search the brain',
            value: query,
            onChange: function (e) { setQuery(e.target.value) },
            onKeyDown: function (e) { if (e.key === 'Enter') void runSearch() }
          }),
          jsx('select', {
            className: 'rounded border border-(--ui-stroke-secondary) bg-transparent px-1 text-xs',
            value: leg,
            onChange: function (e) { setLeg(e.target.value) },
            children: LEGS.map(function (l) {
              return jsx('option', { value: l, children: l }, l)
            })
          })
        ]
      }),
      jsxs('div', {
        className: 'relative flex min-h-0 flex-1 flex-col',
        children: [
          jsx('div', {
            className: 'flex min-h-0 flex-1',
            children: jsx(GraphFrame, {})
          }),
          hitPanel
            ? jsx('div', {
                className: 'absolute inset-x-0 bottom-0',
                children: hitPanel
              })
            : null
        ]
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
