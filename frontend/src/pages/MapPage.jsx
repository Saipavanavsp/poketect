// Interactive region map (Leaflet, CRS.Simple over our own schematic drawing).
// Click to set your location -> nearest gyms and Pokémon Centers with distances.
import L from 'leaflet'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ErrorState, Loading, PokemonImage, TypeBadge, useAsync } from '../components/ui'
import { getMap, getPokemon, pokemonAtPlace } from '../lib/api'
import { MAP_H, MAP_W, fromLatLng, loadLocation, nearest, saveLocation, toLatLng } from '../lib/geo'
import { TYPE_COLORS, capitalize } from '../lib/types'

const icon = (html, size = 18) => L.divIcon({ html, className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2] })
const GYM = (type) =>
  icon(`<svg viewBox="0 0 20 20" width="20" height="20"><path d="M10 1 19 10 10 19 1 10Z" fill="${TYPE_COLORS[type]}" stroke="#4A1220" stroke-width="2"/></svg>`, 20)
const CENTER = icon(
  '<svg viewBox="0 0 20 20" width="18" height="18"><circle cx="10" cy="10" r="8.5" fill="#F7EFDC" stroke="#6B1A2A" stroke-width="2"/><path d="M10 5v10M5 10h10" stroke="#6B1A2A" stroke-width="3"/></svg>',
)
const HERE = icon(
  '<svg viewBox="0 0 26 26" width="26" height="26"><circle cx="13" cy="13" r="11" fill="none" stroke="#E3A33B" stroke-width="3"/><circle cx="13" cy="13" r="4" fill="#E3A33B"/></svg>',
  26,
)

function useLeaflet(ref) {
  const [map, setMap] = useState(null)
  useEffect(() => {
    const m = L.map(ref.current, { crs: L.CRS.Simple, minZoom: -1, maxZoom: 2, zoomSnap: 0.25, attributionControl: false })
    m.fitBounds([[0, 0], [MAP_H, MAP_W]])
    m.setMaxBounds([[-150, -150], [MAP_H + 150, MAP_W + 150]])
    setMap(m)
    const resize = new ResizeObserver(() => m.invalidateSize())
    resize.observe(ref.current)
    return () => {
      resize.disconnect()
      m.remove()
    }
  }, [ref])
  return map
}

export default function MapPage() {
  const [params, setParams] = useSearchParams()
  const region = params.get('region') || 'kanto'
  const placeSlug = params.get('place')
  const { data, error, loading, reload } = useAsync(getMap, [])
  const el = useRef(null)
  const map = useLeaflet(el)
  const layer = useRef(null)
  const [location, setLocation] = useState(() => loadLocation())
  const [placePokemon, setPlacePokemon] = useState(null)
  const [search, setSearch] = useState('')
  const [highlight, setHighlight] = useState({ name: null, places: [], error: null })

  const regionData = data?.[region]
  const here = location.region === region ? location : null
  const place = regionData?.places.find((p) => p.slug === placeSlug)

  const setPlace = (slug) => {
    const next = new URLSearchParams(params)
    if (slug) next.set('place', slug)
    else next.delete('place')
    next.set('region', region)
    setParams(next, { replace: true })
  }

  const moveTo = (loc) => {
    setLocation(loc)
    saveLocation(loc)
  }

  // Draw the region.
  useEffect(() => {
    if (!map || !regionData) return
    layer.current?.remove()
    const g = L.layerGroup().addTo(map)
    layer.current = g
    L.polygon(regionData.land.map(([x, y]) => toLatLng(x, y)), { color: '#8A8077', weight: 2, fillColor: '#F1E6CC', fillOpacity: 1 }).addTo(g)
    regionData.islands.forEach(([x, y, r]) => L.circle(toLatLng(x, y), { radius: r, color: '#8A8077', weight: 2, fillColor: '#F1E6CC', fillOpacity: 1 }).addTo(g))
    regionData.routes.forEach((r) =>
      L.polyline(r.path.map(([x, y]) => toLatLng(x, y)), { color: '#8C2B3D', weight: 4, opacity: 0.55, dashArray: '2 7', lineCap: 'round' })
        .bindTooltip(r.number ? `Route ${r.number}` : 'Path', { sticky: true })
        .addTo(g),
    )
    for (const p of regionData.places) {
      const isTown = p.kind === 'town' || p.kind === 'city'
      const marker = L.circleMarker(toLatLng(p.x, p.y), {
        radius: isTown ? 7 : p.kind === 'route' ? 4 : 5,
        color: isTown ? '#3A3430' : '#6F665E',
        weight: 2,
        fillColor: isTown ? '#3A3430' : p.kind === 'route' ? '#F7EFDC' : '#B9AFA3',
        fillOpacity: 1,
      }).addTo(g)
      if (isTown) marker.bindTooltip(p.name, { permanent: true, direction: 'right', offset: [8, 0], className: 'place-label' })
      else marker.bindTooltip(p.name)
      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e)
        setPlace(p.slug)
      })
    }
    regionData.gyms.forEach((gym) =>
      L.marker(toLatLng(gym.x, gym.y), { icon: GYM(gym.type) }).bindTooltip(`${gym.city} Gym: ${gym.leader} (${capitalize(gym.type)})`).addTo(g),
    )
    regionData.centers.forEach((c) => L.marker(toLatLng(c.x, c.y), { icon: CENTER }).bindTooltip(c.name).addTo(g))
    return () => g.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, regionData])

  // Click the map to set the current location.
  useEffect(() => {
    if (!map || !regionData) return
    const onClick = (e) => {
      const { x, y } = fromLatLng(e.latlng)
      const closest = nearest(regionData.places.filter((p) => p.kind !== 'route'), x, y, 1)[0]
      moveTo({ region, x: Math.round(x), y: Math.round(y), label: closest && closest.distance_km < 3 ? `near ${closest.name}` : 'a spot you picked' })
    }
    map.on('click', onClick)
    return () => map.off('click', onClick)
  }, [map, regionData, region])

  const results = useMemo(() => {
    if (!regionData || !here) return null
    return { gyms: nearest(regionData.gyms, here.x, here.y), centers: nearest(regionData.centers, here.x, here.y) }
  }, [regionData, here])

  // Location marker + lines to the nearest gym and center.
  useEffect(() => {
    if (!map || !here || !results) return
    const g = L.layerGroup().addTo(map)
    L.marker(toLatLng(here.x, here.y), { icon: HERE, zIndexOffset: 1000 }).bindTooltip('You are here').addTo(g)
    for (const target of [results.gyms[0], results.centers[0]]) {
      if (target) L.polyline([toLatLng(here.x, here.y), toLatLng(target.x, target.y)], { color: '#E3A33B', weight: 3, dashArray: '6 6' }).addTo(g)
    }
    return () => g.remove()
  }, [map, here, results])

  // Highlight places for a searched Pokémon.
  useEffect(() => {
    if (!map || !regionData || !highlight.places.length) return
    const g = L.layerGroup().addTo(map)
    highlight.places.forEach((slug) => {
      const p = regionData.places.find((x) => x.slug === slug)
      if (p) L.circleMarker(toLatLng(p.x, p.y), { radius: 14, color: '#6B1A2A', weight: 3, fill: false }).addTo(g)
    })
    return () => g.remove()
  }, [map, regionData, highlight])

  useEffect(() => {
    if (!place) return setPlacePokemon(null)
    let live = true
    setPlacePokemon(undefined)
    pokemonAtPlace(region, place.slug).then((list) => live && setPlacePokemon(list)).catch(() => live && setPlacePokemon([]))
    map?.panTo(toLatLng(place.x, place.y))
    return () => {
      live = false
    }
  }, [place, region, map])

  async function findPokemon(e) {
    e.preventDefault()
    if (!search.trim()) return setHighlight({ name: null, places: [], error: null })
    try {
      const p = await getPokemon(search)
      const places = [...new Set(p.encounters.filter((x) => x.region === region && x.map_place).map((x) => x.map_place))]
      setHighlight({ name: p.display_name, places, error: places.length ? null : `${p.display_name} has no wild encounters recorded in ${capitalize(region)}.` })
    } catch (err) {
      setHighlight({ name: null, places: [], error: err.message })
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[40px]">Region map</h1>
          <p className="text-ink-soft">Click anywhere on the map to set your location.</p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Region">
          {data &&
            Object.entries(data).map(([key, r]) => (
              <button
                key={key}
                role="tab"
                aria-selected={key === region}
                onClick={() => setParams({ region: key }, { replace: true })}
                className={`rounded-md px-3 py-1 font-display text-[17px] font-semibold ${key === region ? 'bg-shell text-paper-soft' : 'bg-paper-edge hover:bg-stone-light'}`}
              >
                {r.label}
              </button>
            ))}
        </div>
      </div>

      {error && <div className="mt-4"><ErrorState error={error} onRetry={reload} /></div>}
      <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div>
          <div className="relative overflow-hidden rounded-xl border-4 border-shell bg-stone">
            {loading && <div className="absolute inset-0 z-[500] flex items-center justify-center"><Loading label="Drawing the map" /></div>}
            <div ref={el} className="h-[420px] w-full sm:h-[540px]" role="application" aria-label={`Map of ${capitalize(region)}`} />
          </div>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[14px] text-ink-soft">
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rotate-45 bg-shell" />Gym</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-shell bg-paper-soft" />Pokémon Center</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-ink" />Town or city</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-stone ring-2 ring-stone-dark" />Landmark</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-led" />You</span>
          </div>
          <p className="mt-2 text-[14px] text-ink-faint">
            This is a schematic map drawn for this project, not official region artwork. Positions are approximate.
          </p>
        </div>

        <aside className="space-y-5">
          <section className="panel p-4">
            <h2 className="text-[22px]">Your location</h2>
            {regionData && (
              <select
                className="field mt-2"
                value=""
                onChange={(e) => {
                  const p = regionData.places.find((x) => x.slug === e.target.value)
                  if (p) moveTo({ region, x: p.x, y: p.y, label: p.name })
                }}
              >
                <option value="">{here ? `At ${here.label}` : 'Choose a town'}</option>
                {regionData.places.filter((p) => p.kind !== 'route').map((p) => <option key={p.slug} value={p.slug}>{p.name}</option>)}
              </select>
            )}
            {!here && <p className="mt-2 text-[15px] text-ink-soft">You're in {capitalize(location.region)} right now. Pick a spot here to measure distances.</p>}
            {results && (
              <div className="mt-3 space-y-3">
                <div>
                  <h3 className="text-[18px]">Nearest gyms</h3>
                  <ol className="mt-1 space-y-1">
                    {results.gyms.map((g) => (
                      <li key={g.id} className="flex items-center justify-between gap-2">
                        <span>
                          <span className="font-semibold">{g.city}</span> <span className="text-ink-soft">{g.leader}</span>{' '}
                          <TypeBadge type={g.type} small />
                        </span>
                        <span className="num shrink-0">{g.distance_km} km</span>
                      </li>
                    ))}
                  </ol>
                </div>
                <div>
                  <h3 className="text-[18px]">Nearest Pokémon Centers</h3>
                  <ol className="mt-1 space-y-1">
                    {results.centers.map((c) => (
                      <li key={c.id} className="flex justify-between gap-2">
                        <span className="font-semibold">{c.city}</span>
                        <span className="num shrink-0">{c.distance_km} km</span>
                      </li>
                    ))}
                  </ol>
                </div>
              </div>
            )}
          </section>

          <section className="panel p-4">
            <h2 className="text-[22px]">Find a Pokémon</h2>
            <form className="mt-2 flex gap-2" onSubmit={findPokemon}>
              <input className="field" placeholder="e.g. Pikachu" value={search} onChange={(e) => setSearch(e.target.value)} />
              <button className="btn btn-shell" type="submit">Find</button>
            </form>
            {highlight.error && <p className="mt-2 text-[15px] text-shell">{highlight.error}</p>}
            {highlight.places.length > 0 && (
              <p className="mt-2 text-[15px]">
                {highlight.name} appears in {highlight.places.length} place{highlight.places.length > 1 ? 's' : ''}, circled on the map.
              </p>
            )}
          </section>

          {place && (
            <section className="panel p-4">
              <div className="flex items-baseline justify-between">
                <h2 className="text-[22px]">{place.name}</h2>
                <button className="text-[14px] text-ink-soft hover:text-shell" onClick={() => setPlace(null)}>Close</button>
              </div>
              {placePokemon === undefined && <Loading label="Looking up encounters" />}
              {placePokemon?.length === 0 && <p className="mt-1 text-[15px] text-ink-soft">No wild Pokémon are recorded here.</p>}
              {placePokemon?.length > 0 && (
                <>
                  <p className="text-[15px] text-ink-soft">{placePokemon.length} wild Pokémon found here</p>
                  <ul className="mt-2 grid max-h-64 grid-cols-4 gap-1 overflow-auto">
                    {placePokemon.map((p) => (
                      <li key={p.id}>
                        <Link to={`/pokemon/${p.name}`} title={p.display_name} className="block rounded hover:bg-paper-edge">
                          <PokemonImage src={p.sprite || p.image} alt={p.display_name} className="h-14 w-14" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  )
}
