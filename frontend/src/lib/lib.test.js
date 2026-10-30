import { describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => {
  const index = [
    { id: 6, name: 'charizard', display_name: 'Charizard' },
    { id: 254, name: 'sceptile', display_name: 'Sceptile' },
    { id: 865, name: 'sirfetchd', display_name: 'Sirfetch’d' },
  ]
  const details = {
    charizard: {
      display_name: 'Charizard', name: 'charizard', types: ['fire', 'flying'], evolves_from: 'charmeleon',
      moves: [
        { name: 'flamethrower', display_name: 'Flamethrower', method: 'level-up', power: 90, type: 'fire' },
        { name: 'inferno', display_name: 'Inferno', method: 'level-up', power: 100, type: 'fire' },
      ],
      evolution: { name: 'charmander', evolves_to: [{ name: 'charmeleon', evolves_to: [{ name: 'charizard', evolves_to: [] }] }] },
    },
    sceptile: {
      display_name: 'Sceptile', name: 'sceptile', types: ['grass'], evolves_from: 'grovyle', moves: [],
      evolution: { name: 'treecko', evolves_to: [{ name: 'grovyle', evolves_to: [{ name: 'sceptile', evolves_to: [] }] }] },
    },
  }
  const map = {
    kanto: {
      gyms: [
        { id: 1, city: 'Pewter City', leader: 'Brock', type: 'rock', badge: 'Boulder Badge', x: 244, y: 188 },
        { id: 2, city: 'Cerulean City', leader: 'Misty', type: 'water', badge: 'Cascade Badge', x: 594, y: 148 },
      ],
      centers: [{ id: 1, name: 'Pewter City Pokémon Center', city: 'Pewter City', x: 216, y: 188 }],
    },
  }
  return {
    hasBackend: false,
    chatUrl: '',
    listPokemon: async () => index,
    getPokemon: async (name) => details[name],
    getMap: async () => map,
    getTrainer: async () => ({
      name: 'Ash Ketchum', hometown: 'Pallet Town', region: 'Kanto', height_ft: 6.2, weight_kg: 79,
      badges: [{ earned: true }, { earned: false }],
      team: [{ level: 78, pokemon: { display_name: 'Charizard' } }, { level: 70, pokemon: { display_name: 'Sceptile' } }],
    }),
    normalizeName: (t) => t.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().trim().replace(/['’.:]/g, '').replace(/[\s_]+/g, '-'),
  }
})

const { distanceKm, nearest, toLatLng, fromLatLng } = await import('./geo')
const { softmaxTop, mirror } = await import('./identify')

describe('mirror', () => {
  it('flips each row of every channel', () => {
    // 3 channels of a 2x2 image: rows [1,2],[3,4] per channel
    const x = new Float32Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    expect(Array.from(mirror(x, 2))).toEqual([2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11])
  })
})
const { sendMessage } = await import('./assistant')

describe('geo', () => {
  it('measures distance in km and sorts nearest first', () => {
    expect(distanceKm(0, 0, 30, 40)).toBe(2.5)
    const ranked = nearest([{ x: 100, y: 0 }, { x: 10, y: 0 }, { x: 50, y: 0 }], 0, 0, 2)
    expect(ranked.map((r) => r.x)).toEqual([10, 50])
  })
  it('round-trips map coordinates', () => {
    const [lat, lng] = toLatLng(230, 580)
    expect(fromLatLng({ lat, lng })).toEqual({ x: 230, y: 580 })
  })
})

describe('softmaxTop', () => {
  it('returns probabilities that sum to at most 1, highest first', () => {
    const top = softmaxTop(new Float32Array([1, 5, 3, 0]), 3)
    expect(top.map(([i]) => i)).toEqual([1, 2, 0])
    expect(top.reduce((a, [, p]) => a + p, 0)).toBeLessThanOrEqual(1)
  })
  it('a temperature above 1 softens the top probability without changing the order', () => {
    const sharp = softmaxTop(new Float32Array([1, 5, 3, 0]), 3)
    const soft = softmaxTop(new Float32Array([1, 5, 3, 0]), 3, 2)
    expect(soft.map(([i]) => i)).toEqual(sharp.map(([i]) => i))
    expect(soft[0][1]).toBeLessThan(sharp[0][1])
  })
})

describe('offline assistant', () => {
  const ask = (q, memory = {}) =>
    sendMessage([{ role: 'user', content: q }], { location: { region: 'kanto', x: 230, y: 200, label: 'Pewter City' } }, { memory })

  it('finds the nearest gym', async () => {
    const r = await ask('Tell me the nearest gym for a battle')
    expect(r.used).toEqual(['find_nearest_gym'])
    expect(r.text).toContain('Brock')
  })
  it('treats hospital as Pokémon Center', async () => {
    const r = await ask('Where is the nearest hospital for my Pokémon?')
    expect(r.used).toEqual(['find_nearest_pokemon_center'])
    expect(r.text).toContain('Pewter City Pokémon Center')
  })
  it('answers attacks from data', async () => {
    const r = await ask('What attacks does Charizard have?')
    expect(r.text).toMatch(/Inferno.*Flamethrower/)
  })
  it('answers evolves-from', async () => {
    const r = await ask('What does Sceptile evolve from?')
    expect(r.text).toContain('evolves from Grovyle')
  })
  it('describes the trainer and team', async () => {
    const r = await ask('Who is the trainer and what is his team?')
    expect(r.text).toContain('Ash Ketchum')
    expect(r.text).toContain('Charizard at level 78')
  })
  it('remembers the last Pokémon for follow-ups', async () => {
    const memory = {}
    await ask('Tell me about Charizard', memory)
    const r = await ask('What does it evolve from?', memory)
    expect(r.text).toContain('Charizard evolves from Charmeleon')
  })
})
