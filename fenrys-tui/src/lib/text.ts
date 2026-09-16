/** Util teks aman-ANSI untuk layout terminal. */

const ANSI_RE = /\x1b\[[0-9;]*m/g

export function stripAnsi(s: string): string {
  return s.replace(ANSI_RE, '')
}

export function visibleWidth(s: string): number {
  return stripAnsi(s).length
}

/** Potong teks (boleh mengandung ANSI) maksimal max sel TERLIHAT. */
export function truncateAnsi(s: string, max: number): string {
  if (max <= 0) return ''
  const plain = stripAnsi(s)
  if (plain.length <= max) return s
  return plain.slice(0, max - 1) + '…'
}

/** Ringkas satu baris: buang newline berlebih, batasi lebar. */
export function compactPreview(s: string, max: number): string {
  const one = s.replace(/\s*\n\s*/g, ' ⏎ ').replace(/\t/g, ' ').trim()
  return truncateAnsi(one, max)
}

/** Pad kanan dengan spasi sampai lebar TERLIHAT = width (aman ANSI). */
export function padEnd(s: string, width: number): string {
  const w = visibleWidth(s)
  return w >= width ? s : s + ' '.repeat(width - w)
}

/** Format durasi ms -> "1m 23s" / "4.2s" / "123ms". */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rem = Math.round(s % 60)
  return `${m}m ${rem}s`
}

/** Format angka besar -> "1.2k". */
export function compactNumber(n: number): string {
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

/** Bungkus teks ke lebar tertentu, pecah di kata (tanpa ANSI). */
export function wrapText(s: string, width: number): string[] {
  if (width <= 0) return [s]
  const words = s.split(/\s+/)
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    if (!cur) {
      cur = w
    } else if ((cur + ' ' + w).length <= width) {
      cur += ' ' + w
    } else {
      lines.push(cur)
      cur = w
    }
  }
  if (cur) lines.push(cur)
  return lines.length ? lines : ['']
}

/** Label fase yang konsisten. */
export function phaseLabel(phase: string | null | undefined): string {
  const p = (phase ?? '').toUpperCase()
  return p || 'RECON'
}
