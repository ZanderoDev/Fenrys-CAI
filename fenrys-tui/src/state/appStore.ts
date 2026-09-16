import type {
  CyberStateExport,
  EventName,
  EventPayloads,
  GatewayInfo,
} from '../types.ts'

/** Satu unit aktivitas di "activity tree" (reasoning/tool/specialist/verify). */
export interface Activity {
  id: number
  kind: 'reasoning' | 'tool' | 'specialist' | 'verification' | 'note'
  /** judul singkat (mis. "execute", "recon", "berpikir") */
  title: string
  /** detail tambahan (rationale, result, kind) */
  detail?: string
  status: 'pending' | 'ok' | 'fail' | 'warn'
  startedAt: number
  elapsedMs?: number
}

/** Satu baris di transkrip. */
export interface TranscriptLine {
  id: number
  role: 'user' | 'agent' | 'system' | 'error'
  text: string
  ts: number
}

export type Phase =
  | 'boot' // menunggu gateway.ready
  | 'idle' // siap input
  | 'busy' // turn sedang berjalan
  | 'dead' // gateway mati

export interface AppState {
  phase: Phase
  info: GatewayInfo | null
  sessionId: string
  /** sesi yang dikenal (dari registry + yang dipakai runtime) */
  knownSessions: string[]
  busySince: number | null
  lines: TranscriptLine[]
  activity: Activity[]
  lastState: CyberStateExport | null
  /** offset scroll transkrip (0 = paling bawah / ikut stream) */
  scroll: number
  showStatePanel: boolean
  notice: string | null // notifikasi sesaat (mis. "sesi diganti")
  fatal: string | null // gateway mati total
  busyVerbSeed: number
}

export const initialState: AppState = {
  phase: 'boot',
  info: null,
  sessionId: 'default',
  knownSessions: ['default'],
  busySince: null,
  lines: [],
  activity: [],
  lastState: null,
  scroll: 0,
  showStatePanel: false,
  notice: null,
  fatal: null,
  busyVerbSeed: 0,
}

let seq = 1
const nid = () => seq++

export type Action =
  | {type: 'ready'; info: GatewayInfo}
  | {type: 'event'; name: EventName; payload: EventPayloads[EventName]}
  | {type: 'user'; text: string}
  | {type: 'agent'; text: string}
  | {type: 'system'; text: string}
  | {type: 'error'; text: string}
  | {type: 'busy'; since: number}
  | {type: 'idle'}
  | {type: 'setSession'; id: string}
  | {type: 'sessions'; list: string[]}
  | {type: 'scroll'; delta: number}
  | {type: 'scrollTo'; value: number}
  | {type: 'toggleState'}
  | {type: 'notice'; text: string | null}
  | {type: 'fatal'; text: string}
  | {type: 'clearTranscript'}
  | {type: 'tickVerb'}

const MAX_ACTIVITY = 200
const MAX_LINES = 5000

function pushLine(s: AppState, role: TranscriptLine['role'], text: string): AppState {
  const lines = [...s.lines, {id: nid(), role, text, ts: Date.now()}]
  return {...s, lines: lines.slice(-MAX_LINES)}
}

function pushActivity(s: AppState, a: Omit<Activity, 'id' | 'startedAt'>): AppState {
  const activity = [...s.activity, {...a, id: nid(), startedAt: Date.now()}]
  return {...s, activity: activity.slice(-MAX_ACTIVITY)}
}

function applyEvent(
  s: AppState,
  name: EventName,
  payload: EventPayloads[EventName],
): AppState {
  switch (name) {
    case 'turn.start': {
      const p = payload as EventPayloads['turn.start']
      return {
        ...pushActivity(s, {
          kind: 'note',
          title: `turn dimulai`,
          detail: p.goal ? p.goal : undefined,
          status: 'pending',
        }),
        activity: [],
        busySince: Date.now(),
        phase: 'busy',
      }
    }
    case 'reasoning.step': {
      const p = payload as EventPayloads['reasoning.step']
      const rationale = (p.rationale ?? '').trim()
      return pushActivity(s, {
        kind: 'reasoning',
        title: 'berpikir',
        detail: rationale || undefined,
        status: 'pending',
      })
    }
    case 'tool.complete': {
      const p = payload as EventPayloads['tool.complete']
      const tool = (p.tool ?? '').trim()
      const result = (p.result ?? '').trim()
      if (!tool) {
        // jalur anti-loop / limit tanpa attempt -> attempt kosong
        return pushActivity(s, {
          kind: 'tool',
          title: 'diblokir anti-loop',
          detail: 'duplikat tanpa progres baru',
          status: 'warn',
        })
      }
      const ok = result === 'success' || result === 'running'
      return pushActivity(s, {
        kind: 'tool',
        title: tool,
        detail: result,
        status: ok ? 'ok' : result === 'error' || result === 'timeout' ? 'fail' : 'warn',
      })
    }
    case 'specialist.step': {
      const p = payload as EventPayloads['specialist.step']
      return pushActivity(s, {
        kind: 'specialist',
        title: p.domain || 'specialist',
        detail: p.kind,
        status: 'pending',
      })
    }
    case 'verification.step': {
      const p = payload as EventPayloads['verification.step']
      const ok = p.status === 'confirmed'
      const bad = p.status === 'failed'
      return pushActivity(s, {
        kind: 'verification',
        title: 'verifikasi',
        detail: p.status,
        status: ok ? 'ok' : bad ? 'fail' : 'pending',
      })
    }
    case 'turn.complete': {
      const p = payload as EventPayloads['turn.complete']
      const st = p.state
      const last = st.history?.at(-1) ?? ''
      let ns: AppState = {
        ...s,
        lastState: st,
        phase: 'idle',
        busySince: null,
      }
      const succeeded = st.halt_reason === 'goal_achieved'
      const stopped = Boolean(st.halt_reason) && !succeeded
      ns = pushActivity(ns, {
        kind: 'note',
        title: succeeded ? 'objektif tercapai ✓' : stopped ? `turn dihentikan · ${st.halt_reason}` : 'turn selesai',
        detail: last || undefined,
        status: succeeded ? 'ok' : stopped ? 'warn' : 'pending',
      })
      // Tampilkan ringkasan akhir agen sebagai baris transkrip agar terbaca
      // di log (bukan hanya di blok aktivitas yang akan hilang).
      if (last) ns = pushLine(ns, 'agent', last)
      return ns
    }
    default:
      return s
  }
}

export function reducer(s: AppState, a: Action): AppState {
  switch (a.type) {
    case 'ready':
      return {...s, phase: s.fatal ? 'dead' : 'idle', info: a.info}
    case 'event':
      return applyEvent(s, a.name, a.payload)
    case 'user':
      return pushLine(s, 'user', a.text)
    case 'agent':
      return pushLine(s, 'agent', a.text)
    case 'system':
      return pushLine(s, 'system', a.text)
    case 'error':
      return pushLine(s, 'error', a.text)
    case 'busy':
      return {...s, phase: 'busy', busySince: a.since}
    case 'idle':
      return {...s, phase: 'idle', busySince: null}
    case 'setSession': {
      const known = s.knownSessions.includes(a.id)
        ? s.knownSessions
        : [...s.knownSessions, a.id]
      return {...s, sessionId: a.id, knownSessions: known, activity: [], lastState: null}
    }
    case 'sessions': {
      const merged = Array.from(new Set([...s.knownSessions, ...a.list]))
      return {...s, knownSessions: merged}
    }
    case 'scroll': {
      const next = Math.max(0, s.scroll + a.delta)
      return {...s, scroll: next}
    }
    case 'scrollTo':
      return {...s, scroll: Math.max(0, a.value)}
    case 'toggleState':
      return {...s, showStatePanel: !s.showStatePanel}
    case 'notice':
      return {...s, notice: a.text}
    case 'fatal':
      return {...s, phase: 'dead', fatal: a.text, busySince: null}
    case 'clearTranscript':
      return {...s, lines: [], activity: [], scroll: 0}
    case 'tickVerb':
      return {...s, busyVerbSeed: s.busyVerbSeed + 1}
    default:
      return s
  }
}
