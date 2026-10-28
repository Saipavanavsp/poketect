// Trainer profile: details, gym badges (click to mark earned) and the team. All editable.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorState, Loading, PokemonImage, TypeBadge } from '../components/ui'
import { getTrainer, hasBackend, resetTrainer, updateBadge, updateTeamMember, updateTrainer } from '../lib/api'
import { TYPE_COLORS, capitalize } from '../lib/types'

// Original geometric badge placeholders (not the official badge artwork).
const SHAPES = [
  'M24 3 45 24 24 45 3 24Z',
  'M24 4c11 9 17 18 17 25a17 17 0 0 1-34 0C7 22 13 13 24 4Z',
  'M24 3l6 14 15 2-11 10 3 15-13-8-13 8 3-15L3 19l15-2Z',
  'M24 4c6 7 14 7 18 6-1 12-6 24-18 33C12 34 7 22 6 10c4 1 12 1 18-6Z',
  'M10 6h28l7 18-7 18H10L3 24Z',
  'M24 3a21 21 0 1 0 0 42 21 21 0 0 0 0-42Zm0 10a11 11 0 1 1 0 22 11 11 0 0 1 0-22Z',
  'M24 3 29 18h16L32 27l5 16-13-10-13 10 5-16L3 18h16Z',
  'M6 6h36v36H6Z',
]

function Badge({ badge, onToggle, busy }) {
  const color = TYPE_COLORS[badge.type]
  return (
    <button
      onClick={onToggle}
      disabled={busy}
      aria-pressed={badge.earned}
      title={`${badge.name} from ${badge.gym_leader}. ${badge.earned ? 'Earned' : 'Not earned yet'}. Click to change.`}
      className="group flex flex-col items-center rounded-lg p-2 text-center hover:bg-paper-edge/60"
    >
      <svg viewBox="0 0 48 48" className="h-14 w-14" aria-hidden>
        <path
          d={SHAPES[(badge.order - 1) % SHAPES.length]}
          fill={badge.earned ? color : 'none'}
          fillRule="evenodd"
          stroke={badge.earned ? '#3A3430' : '#B9AFA3'}
          strokeWidth="2"
          strokeDasharray={badge.earned ? undefined : '4 3'}
        />
      </svg>
      <span className={`mt-1 font-display text-[16px] font-semibold leading-tight ${badge.earned ? '' : 'text-ink-faint'}`}>
        {badge.name.replace(' Badge', '')}
      </span>
      <span className="text-[13px] text-ink-faint">{badge.gym_leader}</span>
    </button>
  )
}

function ProfileForm({ trainer, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: trainer.name, height_ft: trainer.height_ft, weight_kg: trainer.weight_kg,
    hometown: trainer.hometown, region: trainer.region,
  })
  const field = (key, label, type = 'text') => (
    <label className="block">
      <span className="font-display text-[15px] text-ink-soft">{label}</span>
      <input
        className="field mt-0.5"
        type={type}
        step="0.1"
        required
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: type === 'number' ? Number(e.target.value) : e.target.value })}
      />
    </label>
  )
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); onSave(form) }}>
      {field('name', 'Name')}
      {field('hometown', 'Hometown')}
      {field('height_ft', 'Height (ft)', 'number')}
      {field('weight_kg', 'Weight (kg)', 'number')}
      {field('region', 'Region')}
      <div className="flex items-end gap-2">
        <button className="btn btn-shell" type="submit">Save profile</button>
        <button className="btn btn-quiet" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}

function TeamCard({ member, editing, onSave }) {
  const p = member.pokemon
  const [level, setLevel] = useState(member.level)
  const [swap, setSwap] = useState('')
  const [error, setError] = useState(null)
  useEffect(() => setLevel(member.level), [member.level])

  const save = async () => {
    setError(null)
    try {
      await onSave({ level: Number(level), ...(swap ? { pokemon: swap } : {}) })
      setSwap('')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <li className="panel flex flex-col overflow-hidden">
      <Link to={`/pokemon/${p.name}`} className="group flex items-center gap-3 p-3 hover:bg-paper">
        <PokemonImage src={p.image} alt={p.display_name} className="h-24 w-24 shrink-0" />
        <div className="min-w-0">
          <h3 className="truncate text-[24px] group-hover:text-shell">{member.nickname || p.display_name}</h3>
          <p className="num text-[17px] text-ink-soft">Level {member.level}</p>
          <div className="mt-1 flex gap-1">{p.types.map((t) => <TypeBadge key={t} type={t} small />)}</div>
        </div>
      </Link>
      <ul className="grid grid-cols-2 gap-px border-t border-paper-edge bg-paper-edge">
        {member.top_moves.map((m) => (
          <li key={m.name} className="bg-paper-soft px-3 py-1.5">
            <span className="block font-display text-[16px] font-semibold leading-tight">{m.display_name}</span>
            <span className="text-[13px] text-ink-soft">
              {capitalize(m.type)}, {m.power ? `power ${m.power}` : 'status'}
            </span>
          </li>
        ))}
      </ul>
      {editing && (
        <div className="mt-auto grid grid-cols-[80px_1fr] gap-2 border-t border-paper-edge p-3">
          <label>
            <span className="font-display text-[14px] text-ink-soft">Level</span>
            <input className="field" type="number" min="1" max="100" value={level} onChange={(e) => setLevel(e.target.value)} />
          </label>
          <label>
            <span className="font-display text-[14px] text-ink-soft">Swap for</span>
            <input className="field" placeholder="Pokémon name" value={swap} onChange={(e) => setSwap(e.target.value)} />
          </label>
          <button className="btn btn-shell col-span-2" onClick={save}>Save {p.display_name}</button>
          {error && <p role="alert" className="col-span-2 text-[15px] text-shell">{error}</p>}
        </div>
      )}
    </li>
  )
}

export default function Trainer() {
  const [trainer, setTrainer] = useState(null)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [region, setRegion] = useState('kanto')
  const [busy, setBusy] = useState(null)

  const load = () => getTrainer().then(setTrainer).catch(setError)
  useEffect(() => {
    load()
  }, [])

  if (error) return <ErrorState error={error} onRetry={() => { setError(null); load() }} />
  if (!trainer) return <Loading label="Loading trainer" />

  const regions = [...new Set(trainer.badges.map((b) => b.region))]
  const badges = trainer.badges.filter((b) => b.region === region)
  const earned = trainer.badges.filter((b) => b.earned).length

  return (
    <div>
      <section className="grid gap-6 md:grid-cols-[220px_1fr]">
        <div className="lcd flex aspect-square items-end justify-start p-4 md:aspect-auto">
          <p className="font-display text-[64px] font-bold leading-none text-lcd-ink/80">
            {trainer.name.split(' ').map((w) => w[0]).join('')}
          </p>
        </div>
        <div>
          <h1 className="text-[44px]">{trainer.name}</h1>
          {editing ? (
            <ProfileForm
              trainer={trainer}
              onCancel={() => setEditing(false)}
              onSave={async (form) => {
                setTrainer(await updateTrainer(form))
              }}
            />
          ) : (
            <dl className="mt-2 grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-4">
              <div><dt className="font-display text-ink-soft">Height</dt><dd className="num text-[22px] font-semibold">{trainer.height_ft} ft</dd></div>
              <div><dt className="font-display text-ink-soft">Weight</dt><dd className="num text-[22px] font-semibold">{trainer.weight_kg} kg</dd></div>
              <div><dt className="font-display text-ink-soft">Hometown</dt><dd className="text-[18px] font-semibold">{trainer.hometown}</dd></div>
              <div><dt className="font-display text-ink-soft">Region</dt><dd className="text-[18px] font-semibold">{trainer.region}</dd></div>
            </dl>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="btn btn-quiet" onClick={() => setEditing((e) => !e)}>
              {editing ? 'Done editing' : 'Edit trainer'}
            </button>
            {!hasBackend && (
              <button className="btn btn-quiet" onClick={async () => setTrainer(await resetTrainer())}>Restore defaults</button>
            )}
          </div>
          {!hasBackend && (
            <p className="mt-2 text-[14px] text-ink-faint">
              On this static demo, edits are saved in your browser. With the API running they are saved to the database.
            </p>
          )}
        </div>
      </section>

      <section className="mt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b-2 border-shell/70 pb-1">
          <h2 className="text-[28px]">Gym badges</h2>
          <p className="num text-[17px] text-ink-soft">{earned} earned in total</p>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Region">
          {regions.map((r) => (
            <button
              key={r}
              role="tab"
              aria-selected={region === r}
              onClick={() => setRegion(r)}
              className={`rounded-md px-3 py-1 font-display text-[17px] font-semibold ${region === r ? 'bg-shell text-paper-soft' : 'bg-paper-edge hover:bg-stone-light'}`}
            >
              {capitalize(r)} <span className="num opacity-70">{trainer.badges.filter((b) => b.region === r && b.earned).length}/8</span>
            </button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-4 gap-1 sm:grid-cols-8">
          {badges.map((b) => (
            <Badge
              key={b.id}
              badge={b}
              busy={busy === b.id}
              onToggle={async () => {
                setBusy(b.id)
                try {
                  setTrainer(await updateBadge(b.id, !b.earned))
                } catch (err) {
                  setError(err)
                } finally {
                  setBusy(null)
                }
              }}
            />
          ))}
        </div>
        <p className="mt-1 text-[14px] text-ink-faint">Click a badge to mark it earned or not earned.</p>
      </section>

      <section className="mt-10">
        <h2 className="border-b-2 border-shell/70 pb-1 text-[28px]">Team of {trainer.team.length}</h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {trainer.team.map((m) => (
            <TeamCard
              key={m.id}
              member={m}
              editing={editing}
              onSave={async (changes) => setTrainer(await updateTeamMember(m.id, changes))}
            />
          ))}
        </ul>
      </section>
    </div>
  )
}
