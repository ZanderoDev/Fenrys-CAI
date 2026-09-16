import React from 'react'
import {Box, Text} from 'ink'
import TextInput from 'ink-text-input'
import {BRAND} from '../config/brand.ts'
import {hex} from '../theme.ts'
import type {Phase} from '../state/appStore.ts'

interface Props {
  phase: Phase
  value: string
  onChange: (v: string) => void
  onSubmit: (value: string) => void
}

/**
 * Composer: baris input dengan glyph ❯ dan placeholder kontekstual.
 * Nilai input dikontrol parent (App) agar riwayat ↑/↓ bisa mengisi draft.
 */
export function Composer({phase, value, onChange, onSubmit}: Props) {
  const busy = phase === 'busy'
  const disabled = phase !== 'idle'

  const placeholder = busy
    ? 'agen sedang bekerja… (Ctrl+C untuk batalkan)'
    : phase === 'boot'
      ? 'menghubungkan ke gateway…'
      : phase === 'dead'
        ? 'gateway mati — Ctrl+C lalu jalankan ulang'
        : BRAND.welcome

  const submit = (v: string) => {
    const t = v.trim()
    if (!t) return
    onChange('')
    onSubmit(t)
  }

  return (
    <Box
      borderStyle="round"
      borderColor={busy ? hex('muted') : hex('accent')}
      paddingX={1}
    >
      <Text color={hex('accent')} bold>
        {BRAND.prompt}{' '}
      </Text>
      <TextInput
        value={value}
        onChange={onChange}
        onSubmit={submit}
        placeholder={placeholder}
        showCursor={!disabled}
        focus={!disabled}
      />
      {busy && <Text color={hex('muted')}>  ⏳</Text>}
    </Box>
  )
}
