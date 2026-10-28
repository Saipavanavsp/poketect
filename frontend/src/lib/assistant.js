// Conversation engine. With a backend, replies stream from Claude (tool calls run against SQLite).
// Without one, a local intent router runs the same seven tools over the exported data,
// so the live demo still answers from the database rather than guessing.
import { chatUrl, getMap, getPokemon, getTrainer, hasBackend, listPokemon, normalizeName } from './api'
import { nearest } from './geo'
import { findNode } from './speech'

// ------------------------------------------------------------------ tools (same names as the backend)

export const tools = {
  async get_pokemon_info({ name }) {
    const p = await getPokemon(name)
    return { display_name: p.display_name, genus: p.genus, types: p.types, height: p.height, weight: p.weight,
      description: p.description, stats: p.stats, generation: p.generation }
  },
  async get_attacks({ name }) {
    const p = await getPokemon(name)
    const levelUp = p.moves.filter((m) => m.method === 'level-up' && m.power).sort((a, b) => b.power - a.power)
    return { pokemon: p.display_name, total_moves: p.moves.length, top_level_up_moves: levelUp.slice(0, 6) }
  },
  async get_evolutions({ name }) {
    const p = await getPokemon(name)
    return { pokemon: p.display_name, name: p.name, evolves_from: p.evolves_from, chain: p.evolution }
  },
  async find_nearest_gym({ location }) {
    const map = await getMap()
    return { from: location.label, nearest: nearest(map[location.region].gyms, location.x, location.y) }
  },
  async find_nearest_pokemon_center({ location }) {
    const map = await getMap()
    return { from: location.label, nearest: nearest(map[location.region].centers, location.x, location.y) }
  },
  async get_trainer_profile() {
    return getTrainer()
  },
  async identify_last_uploaded_image({ lastScan }) {
    return lastScan || null
  },
}

// ------------------------------------------------------------------ offline intent router

let namePatterns = null
async function findPokemonIn(text) {
  if (!namePatterns) {
    const index = await listPokemon()
    namePatterns = index
      .flatMap((p) => [[normalizeName(p.display_name), p], [p.name, p]])
      .filter(([key]) => key.length > 2)
      .sort((a, b) => b[0].length - a[0].length)
  }
  const hay = `-${normalizeName(text).replace(/[^a-z0-9-]/g, '-')}-`
  const hit = namePatterns.find(([key]) => hay.includes(`-${key}-`))
  return hit ? hit[1] : null
}

const list = (items) => (items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`)

async function offlineReply(text, context, memory) {
  const q = text.toLowerCase()
  const mentioned = await findPokemonIn(text)
  if (mentioned) memory.lastPokemon = mentioned.name
  const subject = mentioned?.name || (/\b(it|its|that one|this one)\b/.test(q) ? memory.lastPokemon : null)
  const used = []
  const call = async (name, args) => {
    used.push(name)
    return tools[name](args)
  }

  if (/\b(gym|battle|leader|badge to)\b/.test(q) && !/\bbadges\b.*\bearned\b/.test(q)) {
    const r = await call('find_nearest_gym', context)
    const [g, next] = r.nearest
    return { used, text: `The closest gym to ${r.from} is ${g.leader}'s ${g.type}-type gym in ${g.city}, about ${g.distance_km} km away. It awards the ${g.badge}.${next ? ` ${next.leader} in ${next.city} is next closest.` : ''}` }
  }
  if (/\b(hospital|center|centre|heal|nurse|injured|hurt)\b/.test(q)) {
    const r = await call('find_nearest_pokemon_center', context)
    const c = r.nearest[0]
    return { used, text: `The nearest Pokémon Center is the ${c.name}, about ${c.distance_km} km from ${r.from}. Nurse Joy will patch your team up.` }
  }
  if (/\b(trainer|team|ash|my pok[eé]mon|badges?)\b/.test(q) && !subject) {
    const t = await call('get_trainer_profile', {})
    const earned = t.badges.filter((b) => b.earned).length
    return { used, text: `Your trainer is ${t.name} from ${t.hometown}, ${t.region}, ${t.height_ft} ft and ${t.weight_kg} kg, with ${earned} badges. The team is ${list(t.team.map((m) => `${m.nickname || m.pokemon.display_name} at level ${m.level}`))}.` }
  }
  if (/\b(scan|scanned|upload|uploaded|picture|photo|image|identified)\b/.test(q)) {
    const r = await call('identify_last_uploaded_image', context)
    if (!r) return { used, text: 'Nothing has been scanned yet. Drop an image on the scanner and ask me again.' }
    const p = r.predictions[0]
    return { used, text: r.confident
      ? `Your last scan was ${p.name}, at ${Math.round(p.confidence * 100)} percent confidence.`
      : `I wasn't sure about the last scan. My best guess was ${p.name} at only ${Math.round(p.confidence * 100)} percent.` }
  }
  if (!subject) {
    return { used, text: 'Ask me about any Pokémon by name, its attacks or evolutions, the nearest gym or Pokémon Center, or your trainer and team.' }
  }
  if (/\b(attack|attacks|move|moves|learn|learns)\b/.test(q)) {
    const r = await call('get_attacks', { name: subject })
    const top = r.top_level_up_moves.slice(0, 4).map((m) => `${m.display_name} (${m.type}, power ${m.power})`)
    return { used, text: top.length
      ? `${r.pokemon} can learn ${r.total_moves} moves. Its strongest level-up attacks are ${list(top)}.`
      : `${r.pokemon} has no damaging level-up moves on record.` }
  }
  if (/\bevol/.test(q)) {
    const r = await call('get_evolutions', { name: subject })
    const node = findNode(r.chain, r.name)
    const into = node?.evolves_to || []
    const from = r.evolves_from ? `${r.pokemon} evolves from ${r.evolves_from.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}` : null
    const to = into.length ? `evolves into ${list(into.map((n) => `${n.display_name}${n.condition ? ` (${n.condition})` : ''}`))}` : null
    if (!from && !to) return { used, text: `${r.pokemon} doesn't evolve.` }
    return { used, text: `${from || r.pokemon}${from && to ? ', and it ' : to ? ' ' : ''}${to || ''}.` }
  }
  const r = await call('get_pokemon_info', { name: subject })
  return { used, text: `${r.display_name}, the ${r.genus}. A ${list(r.types)} type. ${r.description}` }
}

// ------------------------------------------------------------------ public API

/**
 * Send the conversation; calls onDelta with streamed text and onTool for each tool call.
 * Returns { text, used, mode }.
 */
export async function sendMessage(history, context, { onDelta, onTool, memory }) {
  if (hasBackend) {
    try {
      return await streamFromBackend(history, context, { onDelta, onTool })
    } catch (err) {
      if (!err.fallback) throw err
    }
  }
  const last = history[history.length - 1].content
  const reply = await offlineReply(last, context, memory)
  reply.used.forEach((name) => onTool?.(name))
  onDelta?.(reply.text)
  return { ...reply, mode: 'offline' }
}

async function streamFromBackend(history, context, { onDelta, onTool }) {
  const res = await fetch(chatUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: history.map(({ role, content }) => ({ role, content })),
      context: { location: context.location, last_identification: context.lastScan },
    }),
  })
  if (!res.ok || !res.body) throw Object.assign(new Error(`Chat failed (${res.status})`), { fallback: true })
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let text = ''
  const used = []
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let split
    while ((split = buffer.indexOf('\n\n')) >= 0) {
      const chunk = buffer.slice(0, split)
      buffer = buffer.slice(split + 2)
      const event = /^event: (.+)$/m.exec(chunk)?.[1]
      const data = JSON.parse(/^data: (.*)$/m.exec(chunk)?.[1] || '{}')
      if (event === 'text') {
        text += data.delta
        onDelta?.(data.delta)
      } else if (event === 'tool') {
        used.push(data.name)
        onTool?.(data.name)
      } else if (event === 'error') {
        if (!text) throw Object.assign(new Error(data.message), { fallback: /API_KEY|reach/.test(data.message) })
      }
    }
  }
  return { text, used, mode: 'claude' }
}
