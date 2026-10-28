// Live conversation with the Pokédex: typed or spoken questions, streamed and spoken replies.
import { useEffect, useRef, useState } from 'react'
import { hasBackend } from '../lib/api'
import { sendMessage } from '../lib/assistant'
import { loadLocation } from '../lib/geo'
import { loadLastScan } from '../lib/identify'
import { canListen, canSpeak, listen, speak, stopSpeaking } from '../lib/speech'

const SUGGESTIONS = [
  'Tell me the nearest gym for a battle',
  'Where is the nearest hospital for my Pokémon?',
  'What attacks does Charizard have?',
  'What does Sceptile evolve from?',
  'Who is the trainer and what is his team?',
]

const TOOL_LABELS = {
  get_pokemon_info: 'Pokédex entry', get_attacks: 'attacks', get_evolutions: 'evolutions',
  find_nearest_gym: 'gym finder', find_nearest_pokemon_center: 'Pokémon Center finder',
  get_trainer_profile: 'trainer profile', identify_last_uploaded_image: 'last scan',
}

const GREETING = {
  role: 'assistant',
  content: "Pokédex online. Ask me about a Pokémon, the nearest gym or Pokémon Center, or your trainer's team.",
}

export default function Talk() {
  const [messages, setMessages] = useState([GREETING])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const [continuous, setContinuous] = useState(false)
  const [voice, setVoice] = useState(canSpeak)
  const [notice, setNotice] = useState(null)
  const memory = useRef({})
  const stopListening = useRef(() => {})
  const continuousRef = useRef(continuous)
  const log = useRef(null)
  continuousRef.current = continuous

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => () => {
    stopListening.current()
    stopSpeaking()
  }, [])

  async function ask(text) {
    const question = text.trim()
    if (!question || busy) return
    setDraft('')
    setNotice(null)
    const history = [...messages.filter((m) => m !== GREETING), { role: 'user', content: question }]
    setMessages([...messages, { role: 'user', content: question }, { role: 'assistant', content: '', tools: [], pending: true }])
    setBusy(true)
    const patch = (fn) =>
      setMessages((all) => {
        const next = [...all]
        next[next.length - 1] = fn(next[next.length - 1])
        return next
      })
    try {
      const reply = await sendMessage(history, { location: loadLocation(), lastScan: loadLastScan() }, {
        memory: memory.current,
        onDelta: (delta) => patch((m) => ({ ...m, content: m.content + delta })),
        onTool: (name) => patch((m) => ({ ...m, tools: [...m.tools, name] })),
      })
      patch((m) => ({ ...m, pending: false, mode: reply.mode }))
      if (voice) await speak(reply.text)
    } catch (err) {
      patch((m) => ({ ...m, pending: false, content: err.message || 'Something went wrong. Ask again.', error: true }))
    } finally {
      setBusy(false)
    }
    if (continuousRef.current) startListening()
  }

  function startListening() {
    stopSpeaking()
    setListening(true)
    stopListening.current = listen({
      onInterim: (text) => setDraft(text),
      onFinal: (text) => {
        setListening(false)
        ask(text)
      },
      onError: (msg) => {
        setNotice(msg)
        setContinuous(false)
      },
      onEnd: () => setListening(false),
    })
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-[40px]">Talk to the Pokédex</h1>
      <p className="text-ink-soft">
        {hasBackend
          ? 'Answers come from Claude using tools that read this Pokédex\'s own database.'
          : 'This static demo answers with the same Pokédex tools locally. Run the API with a Claude key for open-ended conversation.'}
      </p>

      <section className="mt-5 rounded-2xl bg-shell p-3 shadow-bezel sm:p-4">
        <div ref={log} className="lcd h-[52vh] min-h-[320px] space-y-3 overflow-y-auto p-4" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
              <p
                className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-left text-[17px] leading-snug ${
                  m.role === 'user' ? 'bg-lcd-ink text-lcd' : m.error ? 'bg-shell/15 text-shell' : 'bg-lcd-dark/25'
                }`}
              >
                {m.content || (m.pending ? 'Thinking…' : '')}
              </p>
              {m.tools?.length > 0 && (
                <p className="mt-0.5 font-display text-[13px] text-lcd-ink/70">
                  Checked {[...new Set(m.tools)].map((t) => TOOL_LABELS[t] || t).join(', ')}
                </p>
              )}
            </div>
          ))}
        </div>

        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(draft) }}>
          {canListen && (
            <button
              type="button"
              className={`btn shrink-0 ${listening ? 'bg-led text-ink' : 'bg-paper-soft text-shell hover:bg-paper'}`}
              aria-pressed={listening}
              onClick={() => (listening ? (stopListening.current(), setListening(false)) : startListening())}
            >
              <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${listening ? 'animate-pulse bg-shell' : 'bg-shell'}`} />
              {listening ? 'Listening' : 'Speak'}
            </button>
          )}
          <label className="min-w-0 flex-1">
            <span className="sr-only">Your question</span>
            <input className="field h-full" placeholder="Ask the Pokédex" value={draft} onChange={(e) => setDraft(e.target.value)} />
          </label>
          <button className="btn bg-paper-soft text-shell hover:bg-paper" type="submit" disabled={busy || !draft.trim()}>Send</button>
        </form>

        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-[15px] text-paper-edge">
          {canListen && (
            <label className="flex items-center gap-2">
              <input type="checkbox" className="accent-led" checked={continuous} onChange={(e) => {
                setContinuous(e.target.checked)
                if (e.target.checked && !listening && !busy) startListening()
              }} />
              Keep listening after each reply
            </label>
          )}
          {canSpeak && (
            <label className="flex items-center gap-2">
              <input type="checkbox" className="accent-led" checked={voice} onChange={(e) => { setVoice(e.target.checked); if (!e.target.checked) stopSpeaking() }} />
              Speak replies aloud
            </label>
          )}
          {!canListen && <span>Voice input needs Chrome or Edge. Typing works everywhere.</span>}
        </div>
        {notice && <p role="alert" className="mt-2 text-[15px] text-led">{notice}</p>}
      </section>

      <div className="mt-5">
        <p className="font-display text-[16px] text-ink-soft">Try asking</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="btn btn-quiet text-[16px]" onClick={() => ask(s)} disabled={busy}>{s}</button>
          ))}
        </div>
      </div>
    </div>
  )
}
