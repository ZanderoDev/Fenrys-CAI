import React from 'react'
import {Box, Text} from 'ink'
import {hex, ink as c} from '../theme.ts'
import type {Activity} from '../state/appStore.ts'
import {compactPreview} from '../lib/text.ts'

/**
 * ActivityTree — rails pohon ├─/└─ untuk reasoning/tool/specialist/verify,
 * dengan status berwarna dan auto-collapse detail reasoning panjang.
 */

const STATUS_GLYPH: Record<Activity['status'], {g: string; color: string}> = {
  pending: {g: '●', color: hex('muted')},
  ok: {g: '✓', color: hex('ok')},
  fail: {g: '✗', color: hex('error')},
  warn: {g: '⚠', color: hex('warn')},
}

const KIND_COLOR: Record<Activity['kind'], string> = {
  reasoning: hex('muted'),
  tool: hex('tool'),
  specialist: hex('specialist'),
  verification: hex('verification'),
  note: hex('muted'),
}

function labelFor(a: Activity): string {
  switch (a.kind) {
    case 'reasoning':
      return 'berpikir'
    case 'tool':
      return a.title
    case 'specialist':
      return a.title
    case 'verification':
      return 'verifikasi'
    default:
      return a.title
  }
}

function Line({a, last, width}: {a: Activity; last: boolean; width: number}) {
  const branch = last ? '└─' : '├─'
  const st = STATUS_GLYPH[a.status]
  const kindColor = KIND_COLOR[a.kind]
  const label = labelFor(a)
  const detail = a.detail ? compactPreview(a.detail, Math.max(10, width - 14)) : ''
  return (
    <Box>
      <Text color={hex('border')}>{branch} </Text>
      <Text color={st.color}>{st.g} </Text>
      <Text color={kindColor} bold={a.kind !== 'reasoning'}>
        {label}
      </Text>
      {detail ? <Text color={hex('muted')}> · {detail}</Text> : null}
    </Box>
  )
}

export function ActivityTree({items, width}: {items: Activity[]; width: number}) {
  if (items.length === 0) return null
  return (
    <Box flexDirection="column" marginLeft={1}>
      {items.map((a, i) => (
        <Line key={a.id} a={a} last={i === items.length - 1} width={width} />
      ))}
    </Box>
  )
}

/** Versi "live" dengan header berchevrolet (untuk blok yang sedang berjalan). */
export function ActivityBlock({
  title,
  items,
  width,
  active,
}: {
  title: string
  items: Activity[]
  width: number
  active: boolean
}) {
  return (
    <Box flexDirection="column">
      <Box>
        <Text color={hex('accent')}>{active ? '▾' : '▸'} </Text>
        <Text color={hex('primary')} bold>
          {title}
        </Text>
        <Text color={hex('muted')}>  ({items.length})</Text>
      </Box>
      <ActivityTree items={items} width={width} />
    </Box>
  )
}
