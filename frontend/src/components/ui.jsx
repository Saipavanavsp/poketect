// Small shared pieces: type badge, loading / error / empty states, hooks.
import { useEffect, useState } from 'react'
import { TYPE_COLORS, capitalize } from '../lib/types'

export function TypeBadge({ type, small }) {
  return (
    <span
      className={`inline-block rounded-sm font-display font-semibold text-paper-soft ${small ? 'px-1.5 text-[13px]' : 'px-2.5 py-0.5 text-[15px]'}`}
      style={{ backgroundColor: TYPE_COLORS[type] || '#8A8077' }}
    >
      {capitalize(type)}
    </span>
  )
}

export function Loading({ label = 'Loading' }) {
  return (
    <div role="status" className="flex items-center gap-3 py-10 font-display text-lg text-ink-soft">
      <span className="h-3 w-3 animate-pulse rounded-full bg-led" />
      {label}…
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div role="alert" className="panel border-shell/40 p-5">
      <p className="font-display text-lg font-semibold text-shell">{error?.message || String(error)}</p>
      {onRetry && (
        <button className="btn btn-quiet mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

/** useAsync(fn, deps) -> { data, error, loading, reload } */
export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn()
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}

export function PokemonImage({ src, alt, className = '' }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div className={`flex items-center justify-center bg-paper-edge/60 font-display text-ink-faint ${className}`}>
        No image
      </div>
    )
  }
  return <img src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} className={`object-contain ${className}`} />
}
