// Search and browse all Pokémon, filtered by type and generation. Filters live in the URL.
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ErrorState, Loading, PokemonImage, TypeBadge, useAsync } from '../components/ui'
import { listPokemon, normalizeName } from '../lib/api'
import { GENERATIONS, TYPES, capitalize, dexNo } from '../lib/types'

const PAGE = 96

export default function Browse() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const type = params.get('type') || ''
  const gen = Number(params.get('gen')) || 0
  const [shown, setShown] = useState(PAGE)
  const { data, error, loading, reload } = useAsync(listPokemon, [])

  const set = (key, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
    setShown(PAGE)
  }

  const results = useMemo(() => {
    if (!data) return []
    const key = normalizeName(q)
    return data.filter(
      (p) =>
        (!type || p.types.includes(type)) &&
        (!gen || p.generation === gen) &&
        (!key || p.name.includes(key) || normalizeName(p.display_name).includes(key) || String(p.id) === key),
    )
  }, [data, q, type, gen])

  return (
    <div>
      <h1 className="text-[40px]">Pokédex</h1>
      <p className="text-ink-soft">
        {data ? `${data.length} Pokémon from Kanto to Paldea.` : 'Every Pokémon from Kanto to Paldea.'}
      </p>

      <form className="mt-5 grid gap-3 sm:grid-cols-[2fr_1fr_1fr]" onSubmit={(e) => e.preventDefault()} role="search">
        <label className="block">
          <span className="sr-only">Search by name or number</span>
          <input className="field" placeholder="Search by name or number" value={q} onChange={(e) => set('q', e.target.value)} />
        </label>
        <label className="block">
          <span className="sr-only">Type</span>
          <select className="field" value={type} onChange={(e) => set('type', e.target.value)}>
            <option value="">All types</option>
            {TYPES.map((t) => <option key={t} value={t}>{capitalize(t)}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="sr-only">Generation</span>
          <select className="field" value={gen || ''} onChange={(e) => set('gen', e.target.value)}>
            <option value="">All generations</option>
            {GENERATIONS.map(([g, region]) => <option key={g} value={g}>Gen {g}, {region}</option>)}
          </select>
        </label>
      </form>

      {loading && <Loading label="Loading the Pokédex" />}
      {error && <div className="mt-6"><ErrorState error={error} onRetry={reload} /></div>}
      {data && (
        <>
          <p className="mt-4 font-display text-[16px] text-ink-soft">
            {results.length === data.length ? 'Showing all' : `${results.length} match${results.length === 1 ? '' : 'es'}`}
          </p>
          {results.length === 0 ? (
            <div className="panel mt-3 p-6">
              <p className="font-display text-xl">No Pokémon match those filters.</p>
              <button className="btn btn-quiet mt-3" onClick={() => setParams({}, { replace: true })}>Clear filters</button>
            </div>
          ) : (
            <ul className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-paper-edge bg-paper-edge sm:grid-cols-3 lg:grid-cols-4">
              {results.slice(0, shown).map((p) => (
                <li key={p.id} className="bg-paper-soft">
                  <Link to={`/pokemon/${p.name}`} className="flex items-center gap-3 p-3 hover:bg-paper">
                    <PokemonImage src={p.sprite || p.image} alt="" className="h-16 w-16 shrink-0" />
                    <span className="min-w-0">
                      <span className="num block text-[14px] text-ink-faint">{dexNo(p.id)}</span>
                      <span className="block truncate font-display text-[19px] font-semibold leading-tight">{p.display_name}</span>
                      <span className="mt-1 flex flex-wrap gap-1">
                        {p.types.map((t) => <TypeBadge key={t} type={t} small />)}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {shown < results.length && (
            <div className="mt-5 text-center">
              <button className="btn btn-quiet" onClick={() => setShown((s) => s + PAGE)}>
                Show {Math.min(PAGE, results.length - shown)} more
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
