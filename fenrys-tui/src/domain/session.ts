import {existsSync, readdirSync, statSync} from 'node:fs'
import {join} from 'node:path'

/**
 * Registry sesi — MEMBACA (read-only) metadata sesi dari filesystem.
 * TIDAK PERNAH menulis ke .fenrys-state atau checkpoint. Satu-satunya mutasi
 * sesi tetap lewat protokol gateway (prompt.submit / session.resume).
 */

export interface SessionMeta {
  id: string
  /** sumber: checkpoint sqlite / workspace / runtime */
  sources: string[]
  mtime: number
}

function safeList(dir: string): string[] {
  try {
    if (!existsSync(dir)) return []
    return readdirSync(dir)
  } catch {
    return []
  }
}

/**
 * Kumpulkan kandidat session id yang pernah dipakai, dengan melihat nama
 * direktori di .fenrys-workspaces (per-session CWD). Read-only.
 */
export function discoverSessions(projectRoot: string): SessionMeta[] {
  const out = new Map<string, SessionMeta>()
  const workspaces = join(projectRoot, '.fenrys-workspaces')
  for (const name of safeList(workspaces)) {
    const full = join(workspaces, name)
    try {
      const st = statSync(full)
      if (!st.isDirectory()) continue
      const cur = out.get(name)
      const meta: SessionMeta = cur ?? {id: name, sources: [], mtime: 0}
      meta.sources.push('workspace')
      meta.mtime = Math.max(meta.mtime, st.mtimeMs)
      out.set(name, meta)
    } catch {
      /* abaikan entri tak terbaca */
    }
  }
  return [...out.values()].sort((a, b) => b.mtime - a.mtime)
}

/** Buat session id baru yang unik & mudah dibaca. */
export function newSessionId(prefix = 's'): string {
  const t = new Date()
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  const stamp = `${pad(t.getHours())}${pad(t.getMinutes())}${pad(t.getSeconds())}`
  const rand = Math.random().toString(36).slice(2, 6)
  return `${prefix}-${stamp}-${rand}`
}
