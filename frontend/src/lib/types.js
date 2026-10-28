// Type colours, muted so they sit with the burgundy / cream / warm-gray palette.
export const TYPE_COLORS = {
  normal: '#A59C86', fire: '#C0623A', water: '#4F7A9A', electric: '#B8931F', grass: '#5F8747',
  ice: '#6E9C9B', fighting: '#963A31', poison: '#7E4A7A', ground: '#A08050', flying: '#7F83A8',
  psychic: '#B04F6A', bug: '#838C3A', rock: '#958355', ghost: '#5D5478', dragon: '#4E4C8E',
  dark: '#4F4540', steel: '#7F888E', fairy: '#B87489',
}

export const TYPES = Object.keys(TYPE_COLORS)

export const GENERATIONS = [
  [1, 'Kanto'], [2, 'Johto'], [3, 'Hoenn'], [4, 'Sinnoh'], [5, 'Unova'],
  [6, 'Kalos'], [7, 'Alola'], [8, 'Galar'], [9, 'Paldea'],
]

export const STAT_LABELS = {
  hp: 'HP', attack: 'Attack', defense: 'Defense', sp_attack: 'Sp. Atk', sp_defense: 'Sp. Def', speed: 'Speed',
}

export const dexNo = (id) => `#${String(id).padStart(4, '0')}`
export const capitalize = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s)
export const titleCase = (s) => (s || '').split('-').map(capitalize).join(' ')
