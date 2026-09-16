import React from 'react'
import {Box, Text} from 'ink'
import {BRAND, VERSION} from '../config/brand.ts'
import {hex, ink as c} from '../theme.ts'
import {wolfColored} from '../banner.ts'
import {pickTier} from './Banner.tsx'
import {composeSideBySide, buildInfoLines} from '../lib/compose.ts'
import type {GatewayInfo} from '../types.ts'
import {phaseLabel, truncateAnsi} from '../lib/text.ts'

interface Props {
  cols: number
  rows: number
  info: GatewayInfo | null
  sessionId: string
  phase: string | null
  toolsCount: number
  cwd: string
}

/** Panel sesi: hero serigala + info, digabung per-baris agar stabil. */
export function SessionPanel({cols, rows, info, sessionId, phase, toolsCount, cwd}: Props) {
  const tier = pickTier(cols, rows)
  const providerOk = info?.provider_ready ?? false

  const fields = buildInfoLines(
    [
      {label: 'provider', value: providerOk ? 'siap' : 'BELUM siap'},
      {label: 'tools', value: `${toolsCount} lokal · via MCP`},
      {label: 'session', value: sessionId},
      {label: 'fase', value: phaseLabel(phase)},
      {label: 'cwd', value: cwd},
    ],
    9,
    {
      label: (s) => c.muted(s),
      value: (s) => c.text(s),
    },
  )

  const header = [
    c.primary(`${BRAND.icon} ${BRAND.name} `) + c.muted(`v${VERSION}`),
    '',
    ...fields.map((l, i) => {
      // warnai value provider
      if (i === 0)
        return (
          c.muted('provider ') +
          (providerOk ? c.ok.bold('siap') : c.error.bold('BELUM siap'))
        )
      return l
    }),
  ]
  if (!providerOk) {
    header.push('')
    header.push(c.warn('⚠ Set FENRYS_LLM_ENDPOINT/API_KEY/MODEL agar agen bisa berpikir.'))
  }
  header.push('')
  header.push(c.muted('/help untuk perintah · /status panel state'))

  const innerWidth = Math.max(20, cols - 10)
  let bodyLines: string[]
  if (tier === 'full') {
    bodyLines = composeSideBySide(wolfColored(), header, 4, innerWidth)
  } else {
    bodyLines = header.map((l) => truncateAnsi(l, innerWidth))
  }

  return (
    <Box
      borderStyle="round"
      borderColor={hex('border')}
      paddingX={2}
      marginX={2}
      flexDirection="column"
    >
      {bodyLines.map((line, i) => (
        <Text key={i} wrap="truncate">
          {line}
        </Text>
      ))}
    </Box>
  )
}
