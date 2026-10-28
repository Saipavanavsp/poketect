// Identify a Pokémon image. Uses POST /api/identify when a backend is configured,
// otherwise runs the same ONNX model in the browser with ONNX Runtime Web.
import { hasBackend, identifyOnServer, listPokemon, staticUrl } from './api'

const MEAN = [0.485, 0.456, 0.406]
const STD = [0.229, 0.224, 0.225]
export const THRESHOLD = 0.5
let sessionPromise = null

async function loadSession() {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const ort = await import('onnxruntime-web')
      ort.env.wasm.numThreads = 1 // static hosts can't enable cross-origin isolation for threads
      const [session, labels] = await Promise.all([
        ort.InferenceSession.create(staticUrl('model/pokemon_cnn.onnx'), { executionProviders: ['wasm'] }),
        fetch(staticUrl('model/labels.json')).then((r) => {
          if (!r.ok) throw new Error('Model labels are missing.')
          return r.json()
        }),
      ])
      return { ort, session, labels }
    })()
    sessionPromise.catch(() => (sessionPromise = null))
  }
  return sessionPromise
}

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('That file could not be read as an image.'))
    img.src = src
  })
}

/** Trim transparent padding, centre on a white square, resize, normalise -> Float32 CHW. */
export function preprocess(img, size) {
  const src = document.createElement('canvas')
  src.width = img.naturalWidth || img.width
  src.height = img.naturalHeight || img.height
  const sctx = src.getContext('2d', { willReadFrequently: true })
  sctx.drawImage(img, 0, 0)
  const { data, width, height } = sctx.getImageData(0, 0, src.width, src.height)
  let [x0, y0, x1, y1] = [width, height, -1, -1]
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] > 0) {
        if (x < x0) x0 = x
        if (y < y0) y0 = y
        if (x > x1) x1 = x
        if (y > y1) y1 = y
      }
    }
  }
  if (x1 < 0) [x0, y0, x1, y1] = [0, 0, width - 1, height - 1]
  const w = x1 - x0 + 1
  const h = y1 - y0 + 1
  const side = Math.max(w, h)

  const out = document.createElement('canvas')
  out.width = out.height = size
  const ctx = out.getContext('2d', { willReadFrequently: true })
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, size, size)
  const scale = size / side
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(src, x0, y0, w, h, ((side - w) / 2) * scale, ((side - h) / 2) * scale, w * scale, h * scale)
  const pixels = ctx.getImageData(0, 0, size, size).data
  const tensor = new Float32Array(3 * size * size)
  for (let i = 0; i < size * size; i++) {
    for (let c = 0; c < 3; c++) tensor[c * size * size + i] = (pixels[i * 4 + c] / 255 - MEAN[c]) / STD[c]
  }
  return tensor
}

export function softmaxTop(logits, k) {
  const max = Math.max(...logits)
  const exps = Array.from(logits, (v) => Math.exp(v - max))
  const sum = exps.reduce((a, b) => a + b, 0)
  return exps
    .map((v, i) => [i, v / sum])
    .sort((a, b) => b[1] - a[1])
    .slice(0, k)
}

export async function identify(file) {
  if (hasBackend) return identifyOnServer(file)
  const url = URL.createObjectURL(file)
  try {
    const [{ ort, session, labels }, img, index] = await Promise.all([loadSession(), loadImage(url), listPokemon()])
    const input = new ort.Tensor('float32', preprocess(img, labels.img_size), [1, 3, labels.img_size, labels.img_size])
    const output = await session.run({ [session.inputNames[0]]: input })
    const top = softmaxTop(output[session.outputNames[0]].data, 3)
    const byName = new Map(index.map((p) => [p.name, p]))
    const predictions = top.map(([i, p]) => ({
      name: labels.classes[i],
      confidence: Math.round(p * 10000) / 10000,
      ...byName.get(labels.classes[i]),
    }))
    const confident = predictions[0].confidence >= THRESHOLD
    return { predictions, confident, message: confident ? null : 'Not sure - the top guess is below 50% confidence.' }
  } finally {
    URL.revokeObjectURL(url)
  }
}

const LAST_KEY = 'pokedex-ai.last-scan'
export function saveLastScan(result) {
  try {
    sessionStorage.setItem(LAST_KEY, JSON.stringify({
      top_prediction: result.predictions[0]?.display_name,
      confident: result.confident,
      predictions: result.predictions.map((p) => ({ name: p.display_name || p.name, confidence: p.confidence })),
    }))
  } catch {
    /* ignore */
  }
}
export function loadLastScan() {
  try {
    return JSON.parse(sessionStorage.getItem(LAST_KEY))
  } catch {
    return null
  }
}
