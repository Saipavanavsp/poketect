// Data access. With VITE_API_URL set, everything goes to the FastAPI backend;
// otherwise the app runs serverless from the exported JSON in /data (GitHub Pages build).
const API = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export const hasBackend = Boolean(API)
const BASE = import.meta.env.BASE_URL
const TRAINER_KEY = 'pokedex-ai.trainer.v1'
const cache = new Map()

async function getJSON(url, { fresh = false } = {}) {
  if (!fresh && cache.has(url)) return cache.get(url)
  const request = fetch(url).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || `Request failed (${res.status})`)
    }
    return res.json()
  })
  cache.set(url, request)
  request.catch(() => cache.delete(url))
  return request
}

async function send(method, path, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const staticUrl = (path) => `${BASE}${path}`

export function listPokemon() {
  return hasBackend ? getJSON(`${API}/api/pokemon`) : getJSON(staticUrl('data/index.json'))
}

export function normalizeName(text) {
  return text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
    .replace(/['’.:]/g, '')
    .replace(/[\s_]+/g, '-')
}

export async function resolvePokemon(key) {
  const index = await listPokemon()
  const k = normalizeName(String(key))
  return index.find((p) => String(p.id) === k || p.name === k || normalizeName(p.display_name) === k) || null
}

export async function getPokemon(key) {
  if (hasBackend) return getJSON(`${API}/api/pokemon/${encodeURIComponent(key)}`)
  const hit = await resolvePokemon(key)
  if (!hit) throw new Error(`No Pokédex entry for "${key}".`)
  const [detail, moves] = await Promise.all([
    getJSON(staticUrl(`data/pokemon/${hit.id}.json`)),
    getJSON(staticUrl('data/moves.json')),
  ])
  if (detail.moves.length && Array.isArray(detail.moves[0])) {
    detail.moves = detail.moves.map(([name, method, level]) => ({ name, method, level, ...moves[name] }))
  }
  return detail
}

export function getMap() {
  return hasBackend ? getJSON(`${API}/api/map/regions`) : getJSON(staticUrl('data/map.json'))
}

export async function pokemonAtPlace(region, slug) {
  if (hasBackend) return getJSON(`${API}/api/map/${region}/places/${slug}/pokemon`)
  const [map, index] = await Promise.all([getMap(), listPokemon()])
  const ids = new Set(map[region]?.place_pokemon?.[slug] || [])
  return index.filter((p) => ids.has(p.id))
}

// ---------------------------------------------------------------- trainer
// Static mode keeps edits in this browser (localStorage); backend mode saves them to SQLite.

function readLocalTrainer() {
  try {
    return JSON.parse(localStorage.getItem(TRAINER_KEY) || 'null')
  } catch {
    return null
  }
}

function writeLocalTrainer(profile) {
  try {
    localStorage.setItem(TRAINER_KEY, JSON.stringify(profile))
  } catch {
    /* storage unavailable: edits last for this visit only */
  }
  cache.set('trainer', Promise.resolve(profile))
  return profile
}

export async function getTrainer() {
  if (hasBackend) return getJSON(`${API}/api/trainer`, { fresh: true })
  if (cache.has('trainer')) return cache.get('trainer')
  const local = readLocalTrainer()
  if (local) return local
  const seeded = structuredClone(await getJSON(staticUrl('data/trainer.json')))
  cache.set('trainer', Promise.resolve(seeded))
  return seeded
}

export async function updateTrainer(fields) {
  if (hasBackend) return send('PUT', '/api/trainer', fields)
  return writeLocalTrainer({ ...(await getTrainer()), ...fields })
}

export async function updateBadge(badgeId, earned) {
  if (hasBackend) return send('PUT', `/api/trainer/badges/${badgeId}`, { earned })
  const t = await getTrainer()
  return writeLocalTrainer({ ...t, badges: t.badges.map((b) => (b.id === badgeId ? { ...b, earned } : b)) })
}

function strongestMoves(detail) {
  const powered = detail.moves.filter((m) => m.power)
  powered.sort((a, b) => (detail.types.includes(b.type) - detail.types.includes(a.type)) || b.power - a.power)
  const seen = new Set()
  return powered.filter((m) => !seen.has(m.name) && seen.add(m.name)).slice(0, 4)
}

export async function updateTeamMember(memberId, changes) {
  if (hasBackend) return send('PUT', `/api/trainer/team/${memberId}`, changes)
  const t = await getTrainer()
  const team = await Promise.all(
    t.team.map(async (m) => {
      if (m.id !== memberId) return m
      const next = { ...m }
      if (changes.level != null) next.level = changes.level
      if (changes.nickname != null) next.nickname = changes.nickname || null
      if (changes.pokemon) {
        const detail = await getPokemon(changes.pokemon)
        const { id, name, display_name, types, generation, image, sprite, stats_total } = detail
        next.pokemon = { id, name, display_name, types, generation, image, sprite, stats_total }
        next.top_moves = strongestMoves(detail).map(({ name, display_name, type, power, accuracy, pp }) => ({
          name, display_name, type, power, accuracy, pp,
        }))
      }
      return next
    }),
  )
  return writeLocalTrainer({ ...t, team })
}

export async function resetTrainer() {
  try {
    localStorage.removeItem(TRAINER_KEY)
  } catch {
    /* ignore */
  }
  cache.delete('trainer')
  return getTrainer()
}

// ---------------------------------------------------------------- identify

export async function identifyOnServer(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API}/api/identify`, { method: 'POST', body: form })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Identification failed (${res.status})`)
  return data
}

export const chatUrl = `${API}/api/chat`
