import { NavLink, Route, Routes } from 'react-router-dom'
import Browse from './pages/Browse'
import MapPage from './pages/MapPage'
import PokemonPage from './pages/PokemonPage'
import Scanner from './pages/Scanner'
import Talk from './pages/Talk'
import Trainer from './pages/Trainer'

const NAV = [
  ['/', 'Scanner'],
  ['/browse', 'Pokédex'],
  ['/trainer', 'Trainer'],
  ['/map', 'Map'],
  ['/talk', 'Talk'],
]

function DeviceHeader() {
  return (
    <header className="bg-shell text-paper-soft shadow-bezel">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:py-4">
        {/* The lens and status lights of the device */}
        <div aria-hidden className="relative h-12 w-12 shrink-0 rounded-full border-4 border-paper-soft bg-gradient-to-br from-[#F3D9A0] to-led shadow-[inset_-4px_-4px_0_rgba(0,0,0,.18)] sm:h-14 sm:w-14">
          <span className="absolute left-2 top-2 h-3 w-3 rounded-full bg-paper-soft/80" />
        </div>
        <div aria-hidden className="hidden gap-1.5 self-start pt-1 sm:flex">
          <span className="h-3 w-3 rounded-full bg-shell-light ring-1 ring-black/20" />
          <span className="h-3 w-3 rounded-full bg-stone ring-1 ring-black/20" />
          <span className="h-3 w-3 rounded-full bg-paper-edge ring-1 ring-black/20" />
        </div>
        <NavLink to="/" className="font-display text-[28px] font-bold leading-none text-paper-soft sm:text-[32px]">
          Poketect
        </NavLink>
        <nav className="ml-auto hidden gap-1 md:flex" aria-label="Main">
          {NAV.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `rounded-md px-3 py-1.5 font-display text-[18px] font-semibold transition-colors ${
                  isActive ? 'bg-shell-dark text-paper-soft shadow-inner' : 'text-paper-edge hover:bg-shell-light'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}

function MobileNav() {
  return (
    <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-[1000] grid grid-cols-5 border-t border-shell-dark bg-shell md:hidden">
      {NAV.map(([to, label]) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `py-3 text-center font-display text-[15px] font-semibold ${isActive ? 'bg-shell-dark text-paper-soft' : 'text-paper-edge'}`
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <DeviceHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-6 md:pb-12">
        <Routes>
          <Route path="/" element={<Scanner />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/pokemon/:key" element={<PokemonPage />} />
          <Route path="/trainer" element={<Trainer />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/talk" element={<Talk />} />
          <Route path="*" element={<p className="font-display text-xl">That page isn't in the Pokédex.</p>} />
        </Routes>
      </main>
      <footer className="bg-shell-dark px-4 pb-20 pt-5 text-[14px] leading-relaxed text-stone-light md:pb-5">
        <div className="mx-auto max-w-6xl">
          <p>
            Fan project, not for commercial use. Pokémon names, artwork and sprites belong to Nintendo, Game Freak
            and The Pokémon Company. Data and images come from{' '}
            <a className="underline hover:text-paper" href="https://pokeapi.co" target="_blank" rel="noreferrer">PokéAPI</a>.
          </p>
          <p className="mt-1">Built by Sai Pavan.</p>
        </div>
      </footer>
      <MobileNav />
    </div>
  )
}
