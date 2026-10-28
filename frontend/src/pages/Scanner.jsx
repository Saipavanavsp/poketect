// Home: the scanner. Upload, drag-drop or webcam -> identify -> full Pokédex entry.
import { useEffect, useRef, useState } from 'react'
import PokemonEntry from '../components/PokemonEntry'
import { ErrorState, Loading, PokemonImage } from '../components/ui'
import { getPokemon } from '../lib/api'
import { identify, saveLastScan } from '../lib/identify'

const ARTWORK = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork'
const SAMPLES = [
  ['Pikachu', `${ARTWORK}/25.png`],
  ['Charizard', `${ARTWORK}/6.png`],
  ['Sceptile', `${ARTWORK}/254.png`],
]

function Camera({ onCapture, onClose }) {
  const video = useRef(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let stream
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: 'environment' } })
      .then((s) => {
        stream = s
        if (video.current) video.current.srcObject = s
      })
      .catch(() => setError('Camera access was blocked or no camera was found.'))
    if (!navigator.mediaDevices) setError('This browser has no camera access.')
    return () => stream?.getTracks().forEach((t) => t.stop())
  }, [])
  const capture = () => {
    const v = video.current
    const canvas = document.createElement('canvas')
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    canvas.getContext('2d').drawImage(v, 0, 0)
    canvas.toBlob((blob) => onCapture(new File([blob], 'camera.jpg', { type: 'image/jpeg' })), 'image/jpeg', 0.92)
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3">
      {error ? (
        <p className="font-display text-lg">{error}</p>
      ) : (
        <video ref={video} autoPlay playsInline muted className="max-h-[260px] w-full rounded object-contain" />
      )}
      <div className="flex gap-2">
        {!error && <button className="btn btn-shell" onClick={capture}>Capture</button>}
        <button className="btn btn-quiet" onClick={onClose}>Close camera</button>
      </div>
    </div>
  )
}

export default function Scanner() {
  const input = useRef(null)
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState('idle') // idle | camera | scanning | done | error
  const [error, setError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [selected, setSelected] = useState(null)
  const [entry, setEntry] = useState({ data: null, loading: false, error: null })

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview])

  useEffect(() => {
    if (!selected) return
    let live = true
    setEntry({ data: null, loading: true, error: null })
    getPokemon(selected)
      .then((data) => live && setEntry({ data, loading: false, error: null }))
      .catch((err) => live && setEntry({ data: null, loading: false, error: err }))
    return () => {
      live = false
    }
  }, [selected])

  async function scan(file) {
    if (!file || !file.type.startsWith('image/')) {
      setError(new Error('Choose an image file (PNG, JPG or WebP).'))
      setStatus('error')
      return
    }
    setPreview(URL.createObjectURL(file))
    setStatus('scanning')
    setResult(null)
    setSelected(null)
    setError(null)
    try {
      const res = await identify(file)
      setResult(res)
      saveLastScan(res)
      setSelected(res.predictions[0].name)
      setStatus('done')
    } catch (err) {
      setError(err)
      setStatus('error')
    }
  }

  async function scanSample(url, name) {
    setStatus('scanning')
    try {
      const blob = await fetch(url).then((r) => {
        if (!r.ok) throw new Error('Could not download the sample image.')
        return r.blob()
      })
      await scan(new File([blob], `${name}.png`, { type: blob.type || 'image/png' }))
    } catch (err) {
      setError(err)
      setStatus('error')
    }
  }

  return (
    <div>
      <section className="rounded-2xl bg-shell p-3 shadow-bezel sm:p-5" aria-label="Scanner">
        <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <div
            className={`lcd relative min-h-[300px] overflow-hidden p-4 ${dragging ? 'ring-4 ring-led' : ''} ${status === 'scanning' ? 'scan-sweep' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              scan(e.dataTransfer.files[0])
            }}
          >
            {status === 'camera' ? (
              <Camera onCapture={scan} onClose={() => setStatus(result ? 'done' : 'idle')} />
            ) : preview ? (
              <img src={preview} alt="Image being scanned" className="mx-auto h-[268px] w-full object-contain" />
            ) : (
              <div className="flex h-[268px] flex-col items-start justify-end">
                <p className="font-display text-[34px] font-bold leading-none sm:text-[44px]">Point. Scan. Know.</p>
                <p className="mt-2 max-w-sm text-[16px]">
                  Drop a picture of a Pokémon here and the Pokédex will tell you who it is, its stats, its attacks
                  and how it evolves.
                </p>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-3 text-paper-soft">
            <div className="flex flex-wrap gap-2">
              <button className="btn bg-paper-soft text-shell hover:bg-paper" onClick={() => input.current.click()}>
                Choose a picture
              </button>
              <button className="btn border border-paper-edge/60 text-paper-soft hover:bg-shell-light" onClick={() => setStatus('camera')}>
                Use camera
              </button>
              <input ref={input} type="file" accept="image/*" className="hidden" onChange={(e) => scan(e.target.files[0])} />
            </div>
            <div>
              <p className="font-display text-[16px] text-paper-edge">No picture handy? Scan one of these:</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {SAMPLES.map(([name, url]) => (
                  <button key={name} className="rounded-md bg-shell-dark px-3 py-1 font-display text-[16px] hover:bg-shell-light" onClick={() => scanSample(url, name)}>
                    {name}
                  </button>
                ))}
              </div>
            </div>

            <div className="lcd mt-auto min-h-[150px] p-3" aria-live="polite">
              {status === 'scanning' && <p className="font-display text-lg">Scanning…</p>}
              {status === 'error' && <p className="font-display text-lg">{error?.message}</p>}
              {(status === 'idle' || (status === 'camera' && !result)) && (
                <p className="font-display text-lg text-lcd-ink/70">Waiting for an image.</p>
              )}
              {result && status !== 'scanning' && (
                <div>
                  <p className="font-display text-[19px] font-semibold">
                    {result.confident ? `Identified: ${result.predictions[0].display_name}` : 'Not sure. Best guesses:'}
                  </p>
                  <ol className="mt-2 space-y-1.5">
                    {result.predictions.map((p) => (
                      <li key={p.name}>
                        <button
                          onClick={() => setSelected(p.name)}
                          className={`grid w-full grid-cols-[32px_1fr_52px] items-center gap-2 rounded px-1 text-left hover:bg-lcd-dark/30 ${selected === p.name ? 'bg-lcd-dark/30' : ''}`}
                        >
                          <PokemonImage src={p.sprite || p.image} alt="" className="h-8 w-8" />
                          <span>
                            <span className="font-display text-[17px] font-semibold">{p.display_name || p.name}</span>
                            <span className="mt-0.5 block h-1.5 rounded bg-lcd-dark/40">
                              <span className="block h-full rounded bg-lcd-ink" style={{ width: `${p.confidence * 100}%` }} />
                            </span>
                          </span>
                          <span className="num text-right text-[17px]">{Math.round(p.confidence * 100)}%</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      <div className="mt-8">
        {entry.loading && <Loading label="Opening the entry" />}
        {entry.error && <ErrorState error={entry.error} />}
        {entry.data && (
          <>
            {result && !result.confident && (
              <p className="mb-4 text-ink-soft">
                Showing the top guess. Pick another guess on the screen above if this isn't it.
              </p>
            )}
            <PokemonEntry pokemon={entry.data} />
          </>
        )}
        {!entry.data && !entry.loading && !entry.error && (
          <p className="max-w-prose text-ink-soft">
            Scans run on the trained neural network. The entry for the identified Pokémon appears here, with its
            stats, attacks table, evolution chain and the places it can be found.
          </p>
        )}
      </div>
    </div>
  )
}
