/**
 * The automatic JSX runtime over the dashboard's React instance.
 *
 * esbuild's `--jsx=automatic` emits `jsx`/`jsxs`/`Fragment` imports from
 * `react/jsx-runtime`. On the dashboard there is no such module, so we provide
 * it in terms of `createElement`. `jsxs` (static children) and `jsx` (one child)
 * differ only in how children arrive; `createElement` handles both, and the
 * `key` prop is passed positionally rather than inside props.
 */

import React from './react'

type Props = Record<string, unknown> & { children?: unknown }

function create(type: unknown, props: Props | null, key?: unknown): unknown {
  const { children, ...rest } = props ?? {}
  const args: unknown[] = [type, key === undefined ? rest : { ...rest, key }]

  if (Array.isArray(children)) {
    args.push(...children)
  } else if (children !== undefined) {
    args.push(children)
  }

  return (React as unknown as { createElement: (...a: unknown[]) => unknown }).createElement(...args)
}

export const jsx = create
export const jsxs = create
export const jsxDEV = create
export const Fragment = (React as unknown as { Fragment: unknown }).Fragment
