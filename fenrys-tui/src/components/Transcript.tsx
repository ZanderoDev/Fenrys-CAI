import React from 'react'
import {Box, Text} from 'ink'
import {hex, ink as c} from '../theme.ts'
import type {TranscriptLine} from '../state/appStore.ts'
import {wrapText} from '../lib/text.ts'
import {BRAND} from '../config/brand.ts'

/**
 * Transcript — riwayat percakapan dengan scrollback penuh.
 * Mengubah TranscriptLine + activity menjadi daftar sel teks yang bisa di-scroll
 * (offset dari bawah). Word-wrap sadar lebar.
 */

export interface RenderItem {
  key: string
  text: string
}

const ROLE_META: Record<
  TranscriptLine['role'],
  {label: string; color: string; glyph: string}
> = {
  user: {label: 'kamu', color: hex('tool'), glyph: '›'},
  agent: {label: 'fenrys', color: hex('accent'), glyph: '›'},
  system: {label: 'sys', color: hex('muted'), glyph: '·'},
  error: {label: 'error', color: hex('error'), glyph: '✗'},
}

/** Bangun daftar baris ter-render dari transcript (word-wrap per peran). */
export function buildTranscriptRows(lines: TranscriptLine[], width: number): RenderItem[] {
  const out: RenderItem[] = []
  const contentWidth = Math.max(10, width - 10)
  for (const l of lines) {
    const meta = ROLE_META[l.role]
    const prefix = `${meta.glyph} `
    const wrapped = wrapText(l.text, contentWidth)
    wrapped.forEach((w, i) => {
      const lead = i === 0 ? c[colorKey(meta.color)](`${meta.label} ${prefix}`) : ' '.repeat(meta.label.length + 2)
      out.push({key: `${l.id}:${i}`, text: lead + w})
    })
  }
  return out
}

function colorKey(color: string): 'tool' | 'accent' | 'muted' | 'error' {
  if (color === hex('tool')) return 'tool'
  if (color === hex('accent')) return 'accent'
  if (color === hex('error')) return 'error'
  return 'muted'
}

interface Props {
  lines: TranscriptLine[]
  width: number
  height: number
  scroll: number // 0 = bawah
}

export function Transcript({lines, width, height, scroll}: Props) {
  const rows = buildTranscriptRows(lines, width)
  const total = rows.length
  const maxScroll = Math.max(0, total - height)
  const clamped = Math.min(scroll, maxScroll)
  const end = total - clamped
  const start = Math.max(0, end - height)
  const view = rows.slice(start, end)
  const belowCount = clamped // baris di bawah viewport (saat scroll ke atas)

  return (
    <Box flexDirection="column" height={height} overflow="hidden">
      {view.map((r) => (
        <Text key={r.key} wrap="truncate">
          {r.text}
        </Text>
      ))}
      {belowCount > 0 && (
        <Text color={hex('warn')}>↓ {belowCount} baris di bawah — PgDn untuk kembali</Text>
      )}
    </Box>
  )
}
