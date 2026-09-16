import React from 'react'
import {Box, Text} from 'ink'
import {BRAND} from '../../config/brand.ts'
import {hex} from '../../theme.ts'

export interface SlashDoc {
  name: string
  args?: string
  desc: string
}

export const SLASH_DOCS: SlashDoc[] = [
  {name: '/help', desc: 'tampilkan bantuan ini'},
  {name: '/new', args: '[nama]', desc: 'mulai sesi baru (id unik atau nama pilihan)'},
  {name: '/session', args: '<id>', desc: 'pindah ke sesi lain (lanjut via checkpoint)'},
  {name: '/resume', args: '[id]', desc: 'lanjutkan sesi dari checkpoint terakhir'},
  {name: '/sessions', desc: 'daftar sesi yang dikenal'},
  {name: '/status', desc: 'toggle panel state (flags/hosts/hipotesis)'},
  {name: '/clear', desc: 'bersihkan transkrip di layar'},
  {name: '/exit', desc: 'keluar dari Fenrys'},
]

export function HelpOverlay({cols}: {cols: number}) {
  const width = Math.min(cols - 4, 64)
  return (
    <Box
      borderStyle="round"
      borderColor={hex('accent')}
      paddingX={2}
      paddingY={1}
      flexDirection="column"
      width={width}
      alignSelf="center"
    >
      <Text color={hex('primary')} bold>
        {BRAND.icon} {BRAND.helpHeader}
      </Text>
      <Text> </Text>
      {SLASH_DOCS.map((d) => (
        <Box key={d.name}>
          <Box width={20}>
            <Text color={hex('accent')} bold>
              {d.name}
              {d.args ? <Text color={hex('muted')}> {d.args}</Text> : null}
            </Text>
          </Box>
          <Text color={hex('text')}>{d.desc}</Text>
        </Box>
      ))}
      <Text> </Text>
      <Text color={hex('muted')}>
        Enter kirim · ↑/↓ riwayat · PgUp/PgDn scroll · Ctrl+C batal/keluar
      </Text>
    </Box>
  )
}
