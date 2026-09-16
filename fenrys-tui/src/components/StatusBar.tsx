import React, {useEffect, useState} from 'react'
import {Box, Text} from 'ink'
import {hex} from '../theme.ts'
import {BUSY_VERBS, LONG_RUN_CHARMS, THINK_VERBS, pick} from '../config/verbs.ts'
import {formatDuration, phaseLabel} from '../lib/text.ts'
import type {Phase} from '../state/appStore.ts'

/* Frame spinner braille (animasi halus). */
const SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

interface Props {
  phase: Phase
  busySince: number | null
  cyberPhase: string | null
  evidence: number
  hypotheses: number
  attempts: number
  flags: number
  sessionId: string
  verbSeed: number
  cols: number
}

function useNow(activeMs: number): number {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), activeMs)
    return () => clearInterval(t)
  }, [activeMs])
  return now
}

export function StatusBar({
  phase,
  busySince,
  cyberPhase,
  evidence,
  hypotheses,
  attempts,
  flags,
  sessionId,
  verbSeed,
  cols,
}: Props) {
  const busy = phase === 'busy'
  const now = useNow(busy ? 100 : 1000)
  const elapsed = busySince ? now - busySince : 0
  const spin = SPINNER[Math.floor(now / 80) % SPINNER.length]
  const verb =
    elapsed > 8000
      ? pick(LONG_RUN_CHARMS, verbSeed)
      : busy
        ? pick(BUSY_VERBS, verbSeed)
        : pick(THINK_VERBS, verbSeed)

  // Segmen kiri (pinned) lalu kanan; drop progresif sesuai lebar.
  const left: string[] = []
  if (busy) left.push(`${spin} ${verb}…`)
  else if (phase === 'idle') left.push('● siap')
  else if (phase === 'boot') left.push(`${spin} menghubungkan`)
  else left.push('✕ mati')
  if (busy && cols >= 40) left.push(formatDuration(elapsed))
  left.push(phaseLabel(cyberPhase))
  if (cols >= 56) left.push(`evd ${evidence}`)
  if (cols >= 66) left.push(`hyp ${hypotheses}`)
  if (cols >= 76) left.push(`att ${attempts}`)
  if (flags > 0 && cols >= 50) left.push(`⚑ ${flags}`)

  const statusColor =
    phase === 'busy'
      ? hex('accent')
      : phase === 'idle'
        ? hex('ok')
        : phase === 'boot'
          ? hex('warn')
          : hex('error')

  const leftStr = left.join('  ')
  const rightStr = sessionId
  const rule = (n: number) => '─'.repeat(Math.max(0, n))
  // hitung sisa untuk garis rule
  const used = leftStr.length + rightStr.length + 4
  const fill = Math.max(1, cols - used)

  return (
    <Box height={1} paddingX={1}>
      <Text color={statusColor} bold wrap="truncate">
        {leftStr}
      </Text>
      <Text color={hex('border')}>{` ${rule(Math.min(fill, 200))} `}</Text>
      {cols >= 30 && (
        <Text color={hex('accent')} bold wrap="truncate">
          {rightStr}
        </Text>
      )}
    </Box>
  )
}
