import React from 'react'
import {Box, Text} from 'ink'
import {logoColored, wolfColored, wolfMidColored, LOGO_WIDTH, WOLF_WIDTH, WOLF_HEIGHT} from '../banner.ts'
import {BRAND, TAGLINES} from '../config/brand.ts'
import {hex, ink as c} from '../theme.ts'

export type Tier = 'full' | 'medium' | 'compact' | 'tiny'

export function pickTier(cols: number, rows: number): Tier {
  if (cols >= WOLF_WIDTH + 30 && rows >= WOLF_HEIGHT + 14) return 'full'
  if (cols >= LOGO_WIDTH + 6 && rows >= 26) return 'medium'
  if (cols >= LOGO_WIDTH + 2) return 'compact'
  return 'tiny'
}

/** Banner merek responsif: logo + hero serigala sesuai ruang terminal. */
export function Banner({cols, rows}: {cols: number; rows: number}) {
  const tier = pickTier(cols, rows)
  if (tier === 'tiny') {
    return (
      <Box paddingX={1}>
        <Text color={hex('primary')} bold>
          {BRAND.icon} {BRAND.name}
        </Text>
        <Text color={hex('muted')}> · {TAGLINES.tiny}</Text>
      </Box>
    )
  }
  const logo = logoColored()
  const tagline = tier === 'compact' ? TAGLINES.mid : TAGLINES.full
  return (
    <Box flexDirection="column" alignItems="center" paddingY={0}>
      {logo.map((line, i) => (
        <Text key={i}>{line}</Text>
      ))}
      <Text color={hex('muted')}>{tagline}</Text>
      {tier === 'medium' && (
        <Box marginTop={1} flexDirection="column">
          {wolfMidColored().map((line, i) => (
            <Text key={i}>{line}</Text>
          ))}
        </Box>
      )}
    </Box>
  )
}

/** Hero serigala besar (dipakai di SessionPanel dua kolom). */
export function WolfHero() {
  return (
    <Box flexDirection="column">
      {wolfColored().map((line, i) => (
        <Text key={i}>{line}</Text>
      ))}
    </Box>
  )
}
