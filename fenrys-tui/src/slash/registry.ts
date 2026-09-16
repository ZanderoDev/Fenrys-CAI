import type {AppState, Action} from '../state/appStore.ts'

/**
 * Slash command registry — perintah lokal TUI (tidak menyentuh core).
 * Setiap handler menerima argumen mentah + konteks.
 */

export interface SlashContext {
  state: AppState
  dispatch: React.Dispatch<Action>
  exit: () => void
  showHelp: () => void
  hideHelp: () => void
  toggleStatePanel: () => void
  newSession: (name?: string) => void
  resumeSession: (id: string) => Promise<void> | void
  submitPrompt: (message: string) => Promise<void> | void
  discover: () => string[]
}

type Handler = (args: string, ctx: SlashContext) => void

const sys = (ctx: SlashContext, text: string) => ctx.dispatch({type: 'system', text})
const err = (ctx: SlashContext, text: string) => ctx.dispatch({type: 'error', text})

const handlers: Record<string, Handler> = {
  help: (_a, ctx) => ctx.showHelp(),

  new: (args, ctx) => {
    ctx.newSession(args.trim() || undefined)
    sys(ctx, `Sesi baru aktif.`)
  },

  session: (args, ctx) => {
    const id = args.trim()
    if (!id) {
      err(ctx, 'Pemakaian: /session <id>')
      return
    }
    void ctx.resumeSession(id)
  },

  resume: (args, ctx) => {
    const id = args.trim() || ctx.state.sessionId
    void ctx.resumeSession(id)
  },

  sessions: (_a, ctx) => {
    const fromDisk = ctx.discover()
    const all = Array.from(new Set([...ctx.state.knownSessions, ...fromDisk]))
    if (all.length === 0) {
      sys(ctx, 'Belum ada sesi tersimpan.')
      return
    }
    for (const id of all) {
      const cur = id === ctx.state.sessionId ? ' (aktif)' : ''
      sys(ctx, `  · ${id}${cur}`)
    }
  },

  status: (_a, ctx) => {
    ctx.toggleStatePanel()
  },

  state: (_a, ctx) => ctx.toggleStatePanel(),

  clear: (_a, ctx) => {
    ctx.dispatch({type: 'clearTranscript'})
  },

  exit: (_a, ctx) => ctx.exit(),
  quit: (_a, ctx) => ctx.exit(),
  q: (_a, ctx) => ctx.exit(),
}

/** Jalankan perintah slash. Mengembalikan true jika ditangani. */
export function runSlash(input: string, ctx: SlashContext): boolean {
  const m = input.match(/^\/(\S+)\s*(.*)$/)
  if (!m) return false
  const name = m[1].toLowerCase()
  const args = m[2] ?? ''
  const h = handlers[name]
  if (!h) {
    err(ctx, `Perintah tidak dikenal: /${name} — coba /help`)
    return true
  }
  h(args, ctx)
  return true
}

/** Daftar nama perintah untuk completion. */
export function slashNames(): string[] {
  return Object.keys(handlers).map((n) => `/${n}`)
}
