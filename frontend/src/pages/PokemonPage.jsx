// /pokemon/:key - a full entry with previous / next navigation.
import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import PokemonEntry from '../components/PokemonEntry'
import { ErrorState, Loading, useAsync } from '../components/ui'
import { getPokemon, listPokemon } from '../lib/api'
import { dexNo } from '../lib/types'

export default function PokemonPage() {
  const { key } = useParams()
  const { data, error, loading, reload } = useAsync(() => getPokemon(key), [key])
  const { data: index } = useAsync(listPokemon, [])

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [key])

  const pos = data && index ? index.findIndex((p) => p.id === data.id) : -1
  const prev = pos > 0 ? index[pos - 1] : null
  const next = pos >= 0 && pos < index.length - 1 ? index[pos + 1] : null

  return (
    <div>
      <nav className="mb-4 flex items-center justify-between gap-3 font-display text-[17px]" aria-label="Pokédex order">
        <Link to="/browse" className="text-shell hover:underline">All Pokémon</Link>
        <span className="flex gap-4">
          {prev && <Link className="hover:text-shell" to={`/pokemon/${prev.name}`}>{dexNo(prev.id)} {prev.display_name}</Link>}
          {next && <Link className="hover:text-shell" to={`/pokemon/${next.name}`}>{dexNo(next.id)} {next.display_name}</Link>}
        </span>
      </nav>
      {loading && <Loading label="Opening the entry" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && <PokemonEntry pokemon={data} />}
    </div>
  )
}
