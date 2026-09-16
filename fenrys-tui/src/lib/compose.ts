import {padEnd, visibleWidth, truncateAnsi} from '../lib/text.ts'

/**
 * Gabungkan blok art (multi-baris) dengan kolom info per-baris.
 * Mengembalikan array string yang lebarnya konsisten (totalWidth).
 * Ini menggantikan flex-row Yoga yang tidak andal untuk blok ASCII besar.
 */
export function composeSideBySide(
  artLines: string[],
  infoLines: string[],
  gap: number,
  totalWidth: number,
): string[] {
  const artWidth = Math.max(...artLines.map((l) => visibleWidth(l)), 0)
  const rows = Math.max(artLines.length, infoLines.length)
  const out: string[] = []
  for (let i = 0; i < rows; i++) {
    const art = artLines[i] ?? ''
    const info = infoLines[i] ?? ''
    const artPadded = padEnd(art, artWidth)
    const line = artPadded + ' '.repeat(gap) + info
    out.push(truncateAnsi(line, totalWidth))
  }
  return out
}

/** Bangun kolom info (array string pendek) untuk SessionPanel. */
export interface InfoField {
  label: string
  value: string
}
export function buildInfoLines(
  fields: InfoField[],
  labelWidth: number,
  paint: {label: (s: string) => string; value: (s: string) => string},
): string[] {
  return fields.map(
    (f) => paint.label(f.label.padEnd(labelWidth)) + paint.value(f.value),
  )
}
