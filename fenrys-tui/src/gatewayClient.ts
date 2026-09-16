import {spawn, type ChildProcess} from 'node:child_process'
import {createInterface, type Interface} from 'node:readline'
import {existsSync} from 'node:fs'
import {dirname, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {EventEmitter} from 'node:events'
import type {EventName, EventPayloads} from './types.ts'

// gatewayClient.ts ada di <root>/fenrys-tui/src/ -> root proyek = naik 2 level.
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')

export function resolvePython(root: string = projectRoot): string {
  const candidates = [
    process.env.FENRYS_PYTHON,
    process.env.VIRTUAL_ENV ? resolve(process.env.VIRTUAL_ENV, 'bin/python') : undefined,
    resolve(root, '.venv/bin/python'),
    'python3',
  ]
  for (const c of candidates) {
    if (!c) continue
    if (c === 'python3' || existsSync(c)) return c
  }
  return 'python3'
}

export {projectRoot}

interface Pending {
  resolve: (v: unknown) => void
  reject: (e: Error) => void
  timer?: NodeJS.Timeout
}

/**
 * Klien NDJSON ke gateway Fenrys (`python -m fenrys_cai.tui.entry`).
 * Demultiplex: frame ber-key "event" -> emit('event'); ber-key "result"/"error"
 * -> selesaikan promise request yang id-nya cocok. Toleran baris rusak.
 */
export class GatewayClient extends EventEmitter {
  private child: ChildProcess | null = null
  private rl: Interface | null = null
  private seq = 0
  private pending = new Map<number, Pending>()
  private stderrBuf: string[] = []
  private alive = false
  readonly cwd: string

  constructor(cwd: string = projectRoot) {
    super()
    this.cwd = cwd
  }

  get isAlive(): boolean {
    return this.alive
  }

  get stderrTail(): string[] {
    return this.stderrBuf.slice(-20)
  }

  start(): void {
    if (this.child) return
    const python = resolvePython(this.cwd)
    const child = spawn(python, ['-m', 'fenrys_cai.tui.entry'], {
      cwd: this.cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.child = child
    this.alive = true

    child.on('error', (err) => {
      this.alive = false
      this.emit('fatal', `Gateway gagal dijalankan: ${err.message}`)
    })
    child.on('exit', (code) => {
      this.alive = false
      // gagalkan semua request yang masih menggantung
      for (const [, p] of this.pending) {
        clearTimeout(p.timer)
        p.reject(new Error(`Gateway berhenti (kode ${code ?? 'unknown'})`))
      }
      this.pending.clear()
      this.emit('exit', code)
    })
    child.stderr?.on('data', (d: Buffer) => {
      const text = d.toString()
      for (const line of text.split('\n')) {
        if (line.trim()) this.stderrBuf.push(line)
      }
      if (this.stderrBuf.length > 200) this.stderrBuf.splice(0, this.stderrBuf.length - 200)
      this.emit('stderr', text)
    })

    this.rl = createInterface({input: child.stdout!})
    this.rl.on('line', (raw) => this.onLine(raw))
  }

  private onLine(raw: string): void {
    if (!raw.trim()) return
    let msg: Record<string, unknown>
    try {
      msg = JSON.parse(raw)
    } catch {
      this.emit('protocol_error', raw)
      return
    }
    if (typeof msg.event === 'string') {
      this.emit('event', msg.event as EventName, msg.payload)
      return
    }
    if ('result' in msg || 'error' in msg) {
      const id = typeof msg.id === 'number' ? msg.id : -1
      const p = this.pending.get(id)
      if (p) {
        this.pending.delete(id)
        clearTimeout(p.timer)
        if ('error' in msg) {
          const m = (msg.error as {message?: string})?.message ?? 'unknown error'
          p.reject(new Error(m))
        } else {
          p.resolve(msg.result)
        }
      }
    }
  }

  /** Kirim method; mengembalikan promise result. */
  call<T = unknown>(
    method: string,
    params: Record<string, unknown> = {},
    timeoutMs = 0, // 0 = tanpa timeout (turn bisa lama)
  ): Promise<T> {
    if (!this.alive || !this.child?.stdin) {
      return Promise.reject(new Error('Gateway tidak aktif'))
    }
    const id = ++this.seq
    return new Promise<T>((res, rej) => {
      const timer =
        timeoutMs > 0
          ? setTimeout(() => {
              this.pending.delete(id)
              rej(new Error(`Timeout menunggu ${method}`))
            }, timeoutMs)
          : undefined
      this.pending.set(id, {
        resolve: (v) => res(v as T),
        reject: rej,
        timer,
      })
      const frame = JSON.stringify({id, method, params}) + '\n'
      this.child!.stdin!.write(frame, (err) => {
        if (err) {
          this.pending.delete(id)
          if (timer) clearTimeout(timer)
          rej(err)
        }
      })
    })
  }

  /** Restart proses (dipakai untuk "cancel" = kill + respawn). */
  restart(): void {
    this.stop()
    this.start()
  }

  stop(): void {
    this.alive = false
    try {
      this.rl?.close()
    } catch {}
    try {
      this.child?.stdin?.end()
    } catch {}
    try {
      this.child?.kill()
    } catch {}
    this.rl = null
    this.child = null
  }
}
