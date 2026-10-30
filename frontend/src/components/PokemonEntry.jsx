// The full Pokédex entry: artwork, types, stats chart, description, voice, evolution, attacks, habitats.
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { canSpeak, describeForSpeech, speak, stopSpeaking } from '../lib/speech'
import { STAT_LABELS, TYPE_COLORS, dexNo, titleCase } from '../lib/types'
import { PokemonImage, TypeBadge } from './ui'

function SpeakButton({ pokemon }) {
  const [speaking, setSpeaking] = useState(false)
  if (!canSpeak) return <p className="text-sm text-ink-faint">Voice playback isn't supported in this browser.</p>
  return (
    <button
      className="btn btn-shell"
      aria-pressed={speaking}
      onClick={() => {
        if (speaking) {
          stopSpeaking()
          setSpeaking(false)
        } else {
          speak(describeForSpeech(pokemon), { onStart: () => setSpeaking(true), onEnd: () => setSpeaking(false) })
        }
      }}
    >
      <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${speaking ? 'animate-pulse bg-led' : 'bg-paper-edge'}`} />
      {speaking ? 'Stop' : 'Speak'}
    </button>
  )
}

export function StatsChart({ stats }) {
  const total = Object.values(stats).reduce((a, b) => a + (b || 0), 0)
  return (
    <div>
      <dl className="space-y-1.5">
        {Object.entries(STAT_LABELS).map(([key, label]) => {
          const value = stats[key] || 0
          return (
            <div key={key} className="grid grid-cols-[72px_36px_1fr] items-center gap-2">
              <dt className="font-display text-[15px] text-ink-soft">{label}</dt>
              <dd className="num text-right text-[16px] font-semibold">{value}</dd>
              <div className="h-2.5 rounded-sm bg-paper-edge" aria-hidden>
                <div
                  className={`h-full rounded-sm ${value >= 100 ? 'bg-shell' : value >= 60 ? 'bg-shell-light/80' : 'bg-stone-dark'}`}
                  style={{ width: `${Math.min(100, (value / 200) * 100)}%` }}
                />
              </div>
            </div>
          )
        })}
      </dl>
      <p className="mt-2 font-display text-[15px] text-ink-soft">
        Base stat total <span className="num font-semibold text-ink">{total}</span>
      </p>
    </div>
  )
}

function EvoNode({ node, current }) {
  const here = node.name === current
  return (
    <Link
      to={`/pokemon/${node.name}`}
      className={`flex w-28 shrink-0 flex-col items-center rounded-lg p-2 text-center transition-colors hover:bg-paper-edge/70 ${here ? 'bg-paper-edge ring-2 ring-shell' : ''}`}
      aria-current={here ? 'page' : undefined}
    >
      <PokemonImage src={node.image} alt={node.display_name} className="h-20 w-20" />
      <span className="mt-1 font-display text-[16px] font-semibold leading-tight">{node.display_name}</span>
    </Link>
  )
}

function EvoBranch({ node, current }) {
  return (
    <div className="flex items-center">
      <EvoNode node={node} current={current} />
      {node.evolves_to.length > 0 && (
        <div className="flex flex-col gap-2">
          {node.evolves_to.map((child) => (
            <div key={child.name} className="flex items-center">
              <div className="flex w-24 flex-col items-center px-1 text-center">
                <span className="font-display text-[13px] leading-tight text-ink-soft">{child.condition || 'Evolves'}</span>
                <svg aria-hidden viewBox="0 0 60 12" className="mt-1 h-3 w-16 text-shell">
                  <path d="M0 6h52M46 1l8 5-8 5" fill="none" stroke="currentColor" strokeWidth="2" />
                </svg>
              </div>
              <EvoBranch node={child} current={current} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function EvolutionChain({ chain, current }) {
  if (!chain || chain.evolves_to.length === 0) {
    return (
      <p className="text-ink-soft">
        This Pokémon does not evolve. Evolution is optional, and some species simply stay as they are.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto pb-2">
      <EvoBranch node={chain} current={current} />
    </div>
  )
}

const METHODS = [
  ['level-up', 'Level up'],
  ['machine', 'TM / TR'],
  ['egg', 'Egg'],
  ['tutor', 'Tutor'],
]

export function MovesTable({ moves }) {
  const available = METHODS.filter(([m]) => moves.some((x) => x.method === m))
  const [method, setMethod] = useState(available[0]?.[0] || 'level-up')
  const [sort, setSort] = useState({ key: method === 'level-up' ? 'level' : 'display_name', dir: 1 })
  const rows = useMemo(() => {
    const list = moves.filter((m) => m.method === method)
    const { key, dir } = sort
    return [...list].sort((a, b) => {
      const av = a[key] ?? -1
      const bv = b[key] ?? -1
      return (typeof av === 'string' ? av.localeCompare(bv) : av - bv) * dir
    })
  }, [moves, method, sort])

  if (!moves.length) return <p className="text-ink-soft">No moves on record.</p>
  const header = (key, label, align = 'left') => (
    <th scope="col" className={`px-2 py-2 font-display text-[15px] font-semibold ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button
        className="hover:text-shell"
        onClick={() => setSort((s) => ({ key, dir: s.key === key ? -s.dir : key === 'power' ? -1 : 1 }))}
      >
        {label}
        {sort.key === key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
      </button>
    </th>
  )
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="How the move is learned">
        {available.map(([m, label]) => (
          <button
            key={m}
            role="tab"
            aria-selected={method === m}
            onClick={() => {
              setMethod(m)
              setSort({ key: m === 'level-up' ? 'level' : 'display_name', dir: 1 })
            }}
            className={`rounded-md px-3 py-1 font-display text-[16px] font-semibold ${method === m ? 'bg-shell text-paper-soft' : 'bg-paper-edge text-ink hover:bg-stone-light'}`}
          >
            {label} <span className="num opacity-70">{moves.filter((x) => x.method === m).length}</span>
          </button>
        ))}
      </div>
      <div className="max-h-[440px] overflow-auto rounded-md border border-paper-edge">
        <table className="w-full min-w-[560px] border-collapse text-[15px]">
          <thead className="sticky top-0 bg-paper-edge text-ink">
            <tr>
              {method === 'level-up' && header('level', 'Lv', 'right')}
              {header('display_name', 'Move')}
              {header('type', 'Type')}
              {header('damage_class', 'Kind')}
              {header('power', 'Power', 'right')}
              {header('accuracy', 'Acc.', 'right')}
              {header('pp', 'PP', 'right')}
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={`${m.name}-${m.level}`} className="border-t border-paper-edge odd:bg-paper/50" title={m.effect}>
                {method === 'level-up' && <td className="num px-2 py-1.5 text-right">{m.level || 'Evo'}</td>}
                <td className="px-2 py-1.5 font-semibold">{m.display_name}</td>
                <td className="px-2 py-1.5"><TypeBadge type={m.type} small /></td>
                <td className="px-2 py-1.5 text-ink-soft">{titleCase(m.damage_class)}</td>
                <td className="num px-2 py-1.5 text-right">{m.power ?? '—'}</td>
                <td className="num px-2 py-1.5 text-right">{m.accuracy != null ? `${m.accuracy}%` : '—'}</td>
                <td className="num px-2 py-1.5 text-right">{m.pp ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Habitats({ encounters }) {
  const grouped = useMemo(() => {
    const byLoc = new Map()
    for (const e of encounters) {
      const key = `${e.region}|${e.location}`
      const prev = byLoc.get(key) || { ...e, versions: new Set() }
      e.versions.forEach((v) => prev.versions.add(v))
      prev.min_level = Math.min(prev.min_level ?? 999, e.min_level ?? 999)
      prev.max_level = Math.max(prev.max_level ?? 0, e.max_level ?? 0)
      byLoc.set(key, prev)
    }
    return [...byLoc.values()]
  }, [encounters])
  if (!grouped.length) {
    return <p className="text-ink-soft">No wild encounters are recorded. It may only be obtainable by evolution, gift, trade or event.</p>
  }
  return (
    <ul className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
      {grouped.slice(0, 40).map((e) => (
        <li key={`${e.region}-${e.location}`} className="flex items-baseline justify-between gap-3 border-b border-paper-edge py-1">
          <span>
            {e.map_place ? (
              <Link className="font-semibold text-shell underline decoration-shell/30 hover:decoration-shell" to={`/map?region=${e.region}&place=${e.map_place}`}>
                {e.location_display}
              </Link>
            ) : (
              <span className="font-semibold">{e.location_display}</span>
            )}
            <span className="text-ink-faint"> {titleCase(e.region || 'unknown region')}</span>
          </span>
          <span className="num shrink-0 text-[15px] text-ink-soft">Lv {e.min_level}–{e.max_level}</span>
        </li>
      ))}
    </ul>
  )
}

function moveList(moves) {
  return moves.map((m) => (m.special ? `${m.name} (${m.special})` : m.name)).join(', ') || '—'
}

/** Pokémon GO stats per form, scraped from pokemondb.net/go/pokedex. */
function GoTable({ forms }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[16px]">
        <thead className="font-display text-ink-soft">
          <tr><th className="pr-4">Form</th><th className="pr-4">Attack</th><th className="pr-4">Defense</th><th className="pr-4">HP</th><th className="pr-4">Catch</th><th className="pr-4">Flee</th><th className="pr-4">Fast moves</th><th>Charge moves</th></tr>
        </thead>
        <tbody>
          {forms.map((f) => (
            <tr key={f.form || 'base'} className="border-t border-shell/30 align-top">
              <td className="pr-4 py-1">{f.form || f.name}</td>
              <td className="num pr-4">{f.attack}</td>
              <td className="num pr-4">{f.defense}</td>
              <td className="num pr-4">{f.stamina}</td>
              <td className="num pr-4">{f.catch_rate == null ? '—' : `${f.catch_rate}%`}</td>
              <td className="num pr-4">{f.flee_rate == null ? '—' : `${f.flee_rate}%`}</td>
              <td className="pr-4">{moveList(f.fast_moves)}</td>
              <td>{moveList(f.charge_moves)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 border-b-2 border-shell/70 pb-1 text-[26px]">{title}</h2>
      {children}
    </section>
  )
}

export default function PokemonEntry({ pokemon: p }) {
  const accent = TYPE_COLORS[p.types[0]]
  return (
    <article>
      <div className="grid gap-6 md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="lcd relative flex items-center justify-center p-6" style={{ boxShadow: `inset 0 0 0 3px ${accent}33, inset 0 2px 6px rgba(47,51,38,.35)` }}>
          <PokemonImage src={p.image} alt={p.display_name} className="aspect-square w-full max-w-[340px]" />
          <span className="num absolute left-3 top-2 text-[18px] font-semibold text-lcd-ink/70">{dexNo(p.id)}</span>
        </div>
        <div>
          <h1 className="text-[44px] sm:text-[52px]">{p.display_name}</h1>
          <p className="font-display text-[19px] text-ink-soft">
            {p.genus}, generation {p.generation}
            {p.is_legendary && ', legendary'}
            {p.is_mythical && ', mythical'}
          </p>
          <div className="mt-3 flex gap-2">
            {p.types.map((t) => <TypeBadge key={t} type={t} />)}
          </div>
          <p className="mt-4 max-w-prose text-[18px] leading-[1.7]">{p.description}</p>
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-[16px] sm:grid-cols-3">
            <div><dt className="font-display text-ink-soft">Height</dt><dd className="num text-[18px] font-semibold">{p.height} m</dd></div>
            <div><dt className="font-display text-ink-soft">Weight</dt><dd className="num text-[18px] font-semibold">{p.weight} kg</dd></div>
            <div className="col-span-2 sm:col-span-1">
              <dt className="font-display text-ink-soft">Abilities</dt>
              <dd>
                {p.abilities.map((a, i) => (
                  <span key={a.name} title={a.effect}>
                    {i > 0 && ', '}
                    {a.display_name || titleCase(a.name)}
                    {a.hidden && <span className="text-ink-faint"> (hidden)</span>}
                  </span>
                ))}
              </dd>
            </div>
          </dl>
          <div className="mt-5"><SpeakButton pokemon={p} /></div>
        </div>
      </div>

      <div className="mt-2 grid gap-x-10 md:grid-cols-2">
        <Section title="Base stats"><StatsChart stats={p.stats} /></Section>
        <Section title="Evolution"><EvolutionChain chain={p.evolution} current={p.name} /></Section>
      </div>
      {p.go?.length > 0 && <Section title="Pokémon GO"><GoTable forms={p.go} /></Section>}
      <Section title="Attacks"><MovesTable key={p.id} moves={p.moves} /></Section>
      <Section title="Where to find it"><Habitats encounters={p.encounters} /></Section>
    </article>
  )
}
