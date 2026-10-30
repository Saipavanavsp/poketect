// Map maths shared by the map page and the offline assistant. Mirrors backend/app/geo.py.
export const KM_PER_UNIT = 0.05
export const MAP_W = 1000
export const MAP_H = 700

export const toLatLng = (x, y) => [MAP_H - y, x]
export const fromLatLng = ({ lat, lng }) => ({ x: lng, y: MAP_H - lat })

export function distanceKm(x1, y1, x2, y2) {
  return Math.round(Math.hypot(x2 - x1, y2 - y1) * KM_PER_UNIT * 100) / 100
}

export function nearest(items, x, y, limit = 3) {
  return items
    .map((item) => ({ ...item, distance_km: distanceKm(x, y, item.x, item.y) }))
    .sort((a, b) => a.distance_km - b.distance_km)
    .slice(0, limit)
}

const LOCATION_KEY = 'poketect.location.v1'
const OLD_LOCATION_KEY = 'pokedex-ai.location.v1' // saved before the rename to Poketect
export const DEFAULT_LOCATION = { region: 'kanto', x: 230, y: 580, label: 'Pallet Town' }

export function loadLocation() {
  try {
    return JSON.parse(localStorage.getItem(LOCATION_KEY) || localStorage.getItem(OLD_LOCATION_KEY)) || DEFAULT_LOCATION
  } catch {
    return DEFAULT_LOCATION
  }
}

export function saveLocation(loc) {
  try {
    localStorage.setItem(LOCATION_KEY, JSON.stringify(loc))
  } catch {
    /* ignore */
  }
}
