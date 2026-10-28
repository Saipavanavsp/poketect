// Web Speech API wrappers: SpeechSynthesis for the Pokédex voice, SpeechRecognition for the mic.

export const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window
const Recognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
export const canListen = Boolean(Recognition)

function pickVoice() {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.startsWith('en'))
  const preferred = ['Google UK English Male', 'Microsoft David', 'Microsoft Mark', 'Daniel', 'Alex']
  return voices.find((v) => preferred.some((p) => v.name.includes(p))) || voices[0] || null
}

/** Speak in a flat, slightly low "device" voice. Resolves when finished or cancelled. */
export function speak(text, { onStart, onEnd } = {}) {
  if (!canSpeak || !text) return Promise.resolve()
  window.speechSynthesis.cancel()
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text.replace(/[#*_]/g, ''))
    const voice = pickVoice()
    if (voice) utterance.voice = voice
    utterance.pitch = 0.55
    utterance.rate = 1.02
    utterance.onstart = () => onStart?.()
    utterance.onend = utterance.onerror = () => {
      onEnd?.()
      resolve()
    }
    window.speechSynthesis.speak(utterance)
  })
}

export function stopSpeaking() {
  if (canSpeak) window.speechSynthesis.cancel()
}

/** One utterance of speech-to-text. Returns a stop() function. */
export function listen({ onInterim, onFinal, onError, onEnd }) {
  if (!Recognition) {
    onError?.('Voice input needs Chrome or Edge.')
    return () => {}
  }
  const rec = new Recognition()
  rec.lang = 'en-US'
  rec.interimResults = true
  rec.continuous = false
  rec.onresult = (event) => {
    let text = ''
    for (const result of event.results) text += result[0].transcript
    const done = event.results[event.results.length - 1].isFinal
    if (done) onFinal?.(text.trim())
    else onInterim?.(text)
  }
  rec.onerror = (event) => {
    if (event.error !== 'no-speech' && event.error !== 'aborted') {
      onError?.(event.error === 'not-allowed' ? 'Microphone access was blocked.' : `Voice input error: ${event.error}`)
    }
  }
  rec.onend = () => onEnd?.()
  rec.start()
  return () => rec.abort()
}

export function describeForSpeech(p) {
  const types = p.types.join(' and ')
  const parts = [
    `${p.display_name}. The ${p.genus || 'Pokémon'}.`,
    `Type: ${types}.`,
    p.description,
    `Height ${p.height} metres. Weight ${p.weight} kilograms.`,
  ]
  if (p.evolves_from) parts.push(`It evolves from ${p.evolves_from.replace(/-/g, ' ')}.`)
  const next = findNode(p.evolution, p.name)?.evolves_to || []
  if (next.length) parts.push(`It evolves into ${next.map((n) => n.display_name).join(' or ')}.`)
  return parts.filter(Boolean).join(' ')
}

export function findNode(node, name) {
  if (!node) return null
  if (node.name === name) return node
  for (const child of node.evolves_to) {
    const hit = findNode(child, name)
    if (hit) return hit
  }
  return null
}
