import {Chalk} from 'chalk'

// Paksa truecolor: tanpa ini, saat stdout bukan TTY (atau FORCE_COLOR tidak
// diset) chalk turun ke level 0 dan semua warna hex hilang.
const chalk = new Chalk({level: 3})

/** Benih warna identitas "serigala malam" — beda total dari palet emas. */
export const SEEDS = {
  primary: '#E8E8E8', // putih es — brand, heading
  accent: '#50FA7B', // aurora hijau — aksi, ok, prompt
  border: '#6272A4', // biru keabu — border panel, rails
  text: '#F8F8F2', // teks utama
  muted: '#7B88A8', // metadata, rails, dim
  surface: '#282A36', // panel bg
  tool: '#8BE9FD', // cyan — tool calls
  specialist: '#BD93F9', // ungu — specialist
  verification: '#F1FA8C', // kuning pucat — verifikasi
  error: '#FF5555',
  ok: '#50FA7B',
  warn: '#FFB86C',
  selection: '#3A3F55',
} as const

export type Seed = keyof typeof SEEDS

const hex = (s: Seed) => SEEDS[s]

/** Warna siap pakai sebagai fungsi chalk (untuk penggunaan bebas). */
export const ink = {
  primary: chalk.hex(hex('primary')),
  accent: chalk.hex(hex('accent')),
  border: chalk.hex(hex('border')),
  text: chalk.hex(hex('text')),
  muted: chalk.hex(hex('muted')),
  surface: chalk.hex(hex('surface')),
  tool: chalk.hex(hex('tool')),
  specialist: chalk.hex(hex('specialist')),
  verification: chalk.hex(hex('verification')),
  error: chalk.hex(hex('error')),
  ok: chalk.hex(hex('ok')),
  warn: chalk.hex(hex('warn')),
}

export {hex}

/** Gradient ladder untuk ASCII art: petakan indeks baris -> salah satu warna. */
export function ladder(colors: string[], row: number, rows: number): string {
  if (colors.length === 0) return SEEDS.primary
  const t = rows <= 1 ? 0 : row / (rows - 1)
  const idx = Math.min(colors.length - 1, Math.floor(t * colors.length))
  return colors[idx]
}

export const ART_GRADIENT = [SEEDS.primary, SEEDS.accent, SEEDS.border, SEEDS.muted]
