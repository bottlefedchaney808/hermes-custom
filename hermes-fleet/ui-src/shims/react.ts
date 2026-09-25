/**
 * React, for the WEB DASHBOARD build only.
 *
 * The desktop loader resolves a real `react` specifier; the dashboard does not —
 * it hands the app's own React instance to plugins on
 * `window.__HERMES_PLUGIN_SDK__`. Importing a second copy of React would give
 * the widgets their own hook dispatcher and every `useState` would throw. So the
 * dashboard build aliases `react` to this module, and one widget source compiles
 * for both hosts.
 */

const SDK = (window as unknown as { __HERMES_PLUGIN_SDK__?: { React?: unknown; hooks?: Record<string, unknown> } })
  .__HERMES_PLUGIN_SDK__

if (!SDK?.React) {
  throw new Error('hermes-fleet: window.__HERMES_PLUGIN_SDK__.React is missing — dashboard SDK not loaded')
}

const React = SDK.React as Record<string, never> & {
  createElement: (...args: unknown[]) => unknown
  Fragment: unknown
}

// Prefer the SDK's curated `hooks` bag when present; fall back to React itself,
// which is what the desktop-equivalent path uses.
const hooks = (SDK.hooks ?? {}) as Record<string, unknown>
const pick = (name: string) => hooks[name] ?? (React as unknown as Record<string, unknown>)[name]

export const useCallback = pick('useCallback') as never
export const useContext = pick('useContext') as never
export const useEffect = pick('useEffect') as never
export const useMemo = pick('useMemo') as never
export const useRef = pick('useRef') as never
export const useState = pick('useState') as never
export const createElement = React.createElement
export const Fragment = React.Fragment

export default React
