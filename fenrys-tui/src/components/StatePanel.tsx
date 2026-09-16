import React from 'react'
import {Box, Text} from 'ink'
import {hex, ink as c} from '../theme.ts'
import type {CyberStateExport} from '../types.ts'
import {compactPreview, phaseLabel} from '../lib/text.ts'

/**
 * StatePanel — ringkasan state.hasil turn.complete: flags, hosts, services,
 * hypotheses + confidence, dan dead ends. Toggle via /status.
 */
export function StatePanel({state, cols}: {state: CyberStateExport | null; cols: number}) {
  const width = Math.min(cols - 4, 96)
  const cw = Math.max(16, width - 6)
  if (!state) {
    return (
      <Box
        borderStyle="round"
        borderColor={hex('border')}
        paddingX={2}
        width={width}
        alignSelf="center"
      >
        <Text color={hex('muted')}>
          ◆ State kosong — jalankan satu turn dulu (kirim objektif), lalu /status.
        </Text>
      </Box>
    )
  }

  const hypStatusColor = (s: string): string =>
    s === 'confirmed' || s === 'supported'
      ? hex('ok')
      : s === 'refuted'
        ? hex('error')
        : s === 'testing'
          ? hex('verification')
          : hex('muted')

  return (
    <Box
      borderStyle="round"
      borderColor={hex('border')}
      paddingX={2}
      flexDirection="column"
      width={width}
      alignSelf="center"
    >
      <Text color={hex('primary')} bold>
        ◆ State Agen — fase {phaseLabel(state.phase)} {state.completed ? c.ok('· tercapai ✓') : ''}
      </Text>

      {/* FLAGS */}
      <Box marginTop={1} flexDirection="column">
        <Text color={hex('verification')} bold>
          ⚑ Flags ({state.flags.length})
        </Text>
        {state.flags.length === 0 && <Text color={hex('muted')}>  (belum ada)</Text>}
        {state.flags.slice(0, 5).map((f, i) => (
          <Text key={i} color={hex('ok')}>
            {'  '}🏁 {compactPreview(f, cw - 4)}
          </Text>
        ))}
      </Box>

      {/* HOSTS + SERVICES */}
      <Box marginTop={1}>
        <Box flexDirection="column" width="50%">
          <Text color={hex('tool')} bold>
            ◈ Hosts ({state.hosts.length})
          </Text>
          {state.hosts.slice(0, 4).map((h) => (
            <Text key={h.id} color={hex('text')} wrap="truncate">
              {'  '}· {h.address} {h.hostname ? `(${h.hostname})` : ''}
            </Text>
          ))}
          {state.hosts.length === 0 && <Text color={hex('muted')}>  —</Text>}
        </Box>
        <Box flexDirection="column" width="50%">
          <Text color={hex('tool')} bold>
            ◈ Services ({state.services.length})
          </Text>
          {state.services.slice(0, 4).map((s) => (
            <Text key={s.id} color={hex('text')} wrap="truncate">
              {'  '}· :{s.port}/{s.protocol} {s.service}
            </Text>
          ))}
          {state.services.length === 0 && <Text color={hex('muted')}>  —</Text>}
        </Box>
      </Box>

      {/* HYPOTHESES */}
      <Box marginTop={1} flexDirection="column">
        <Text color={hex('specialist')} bold>
          ◆ Hipotesis ({state.hypotheses.length})
        </Text>
        {state.hypotheses.slice(0, 4).map((h) => (
          <Box key={h.id}>
            <Text color={hypStatusColor(h.status)}>  ● </Text>
            <Text color={hex('text')} wrap="truncate">
              {compactPreview(h.statement, cw - 18)}
            </Text>
            <Text color={hex('muted')}>  {Math.round(h.confidence * 100)}% {h.status}</Text>
          </Box>
        ))}
        {state.hypotheses.length === 0 && <Text color={hex('muted')}>  —</Text>}
      </Box>

      {/* DEAD ENDS */}
      {state.dead_ends.length > 0 && (
        <Box marginTop={1} flexDirection="column">
          <Text color={hex('warn')} bold>
            ⚠ Dead ends ({state.dead_ends.length})
          </Text>
          {state.dead_ends.slice(0, 2).map((d) => (
            <Text key={d.id} color={hex('muted')} wrap="truncate">
              {'  '}· {compactPreview(d.reason, cw - 4)}
            </Text>
          ))}
        </Box>
      )}
    </Box>
  )
}
