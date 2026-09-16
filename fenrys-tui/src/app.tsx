import React, {useCallback, useEffect, useMemo, useReducer, useRef, useState} from 'react'
import {Box, Text, useApp, useInput, useStdout, Static} from 'ink'
import {GatewayClient, projectRoot} from './gatewayClient.ts'
import {reducer, initialState} from './state/appStore.ts'
import type {EventName, EventPayloads, PromptSubmitResult, SessionResumeResult} from './types.ts'
import {discoverSessions, newSessionId} from './domain/session.ts'
import {Banner} from './components/Banner.tsx'
import {SessionPanel} from './components/SessionPanel.tsx'
import {StatusBar} from './components/StatusBar.tsx'
import {Composer} from './components/Composer.tsx'
import {ActivityBlock} from './components/ActivityTree.tsx'
import {HelpOverlay} from './components/overlays/HelpOverlay.tsx'
import {StatePanel} from './components/StatePanel.tsx'
import {BRAND} from './config/brand.ts'
import {hex, ink as c} from './theme.ts'
import {runSlash, type SlashContext} from './slash/registry.ts'

export function App() {
  const {exit} = useApp()
  const {stdout} = useStdout()
  const [state, dispatch] = useReducer(reducer, initialState)
  const [showHelp, setShowHelp] = useState(false)
  const [history, setHistory] = useState<string[]>([])
  const histIdx = useRef(-1)
  const [draft, setDraft] = useState('')
  const gwRef = useRef<GatewayClient | null>(null)

  const cols = stdout?.columns ?? 100
  const rows = stdout?.rows ?? 30

  /* ---- gateway lifecycle ---- */
  useEffect(() => {
    const gw = new GatewayClient(projectRoot)
    gwRef.current = gw
    gw.on('event', (name: EventName, payload: EventPayloads[EventName]) => {
      if (name === 'gateway.ready') {
        dispatch({type: 'ready', info: payload as EventPayloads['gateway.ready']})
      }
      dispatch({type: 'event', name, payload})
    })
    gw.on('fatal', (m: string) => dispatch({type: 'fatal', text: m}))
    gw.on('exit', (code: number | null) => {
      if (code !== 0 && code !== null) {
        dispatch({type: 'fatal', text: `Gateway berhenti (kode ${code})`})
      }
    })
    gw.start()
    // daftar sesi dari disk (read-only)
    const metas = discoverSessions(projectRoot)
    if (metas.length) dispatch({type: 'sessions', list: metas.map((m) => m.id)})
    return () => gw.stop()
  }, [])

  /* ---- timer untuk verb & status ---- */
  useEffect(() => {
    if (state.phase !== 'busy') return
    const t = setInterval(() => dispatch({type: 'tickVerb'}), 2500)
    return () => clearInterval(t)
  }, [state.phase])

  /* ---- pengiriman prompt ---- */
  const submitPrompt = useCallback(
    async (message: string) => {
      const gw = gwRef.current
      if (!gw || !gw.isAlive) {
        dispatch({type: 'error', text: 'Gateway tidak aktif.'})
        return
      }
      dispatch({type: 'user', text: message})
      dispatch({type: 'busy', since: Date.now()})
      try {
        await gw.call<PromptSubmitResult>('prompt.submit', {
          session_id: state.sessionId,
          message,
        })
        // turn.complete sudah mengatur idle via event; pastikan:
        dispatch({type: 'idle'})
      } catch (e) {
        dispatch({type: 'error', text: (e as Error).message})
        dispatch({type: 'idle'})
      }
    },
    [state.sessionId],
  )

  const resumeSession = useCallback(
    async (id: string) => {
      const gw = gwRef.current
      if (!gw || !gw.isAlive) return
      dispatch({type: 'busy', since: Date.now()})
      try {
        const res = await gw.call<SessionResumeResult>('session.resume', {session_id: id})
        dispatch({type: 'setSession', id})
        if (res?.state) {
          dispatch({type: 'event', name: 'turn.complete', payload: {state: res.state}})
        }
        dispatch({type: 'notice', text: `Sesi "${id}" dimuat.`})
      } catch (e) {
        dispatch({type: 'error', text: `Gagal resume "${id}": ${(e as Error).message}`})
      } finally {
        dispatch({type: 'idle'})
      }
    },
    [],
  )

  /* ---- slash command context ---- */
  const slashCtx: SlashContext = useMemo(
    () => ({
      state,
      dispatch,
      exit: () => {
        gwRef.current?.stop()
        exit()
      },
      showHelp: () => setShowHelp(true),
      hideHelp: () => setShowHelp(false),
      toggleStatePanel: () => dispatch({type: 'toggleState'}),
      newSession: (name?: string) => {
        const id = name?.trim() || newSessionId()
        dispatch({type: 'setSession', id})
        dispatch({type: 'notice', text: `Sesi baru: ${id}`})
      },
      resumeSession,
      submitPrompt,
      discover: () => discoverSessions(projectRoot).map((m) => m.id),
    }),
    [state, exit, resumeSession, submitPrompt],
  )

  /* ---- handler submit dari composer ---- */
  const onSubmit = useCallback(
    (value: string) => {
      setHistory((h) => (h[h.length - 1] === value ? h : [...h, value]))
      histIdx.current = -1
      if (value.startsWith('/')) {
        runSlash(value, slashCtx)
        return
      }
      if (state.phase !== 'idle') return
      void submitPrompt(value)
    },
    [slashCtx, state.phase, submitPrompt],
  )

  /* ---- keyboard ---- */
  useInput((input, key) => {
    if (key.ctrl && input === 'c') {
      if (state.phase === 'busy') {
        // cancel = kill + respawn gateway; sesi aman di checkpoint
        gwRef.current?.restart()
        dispatch({type: 'idle'})
        dispatch({type: 'notice', text: 'Dibatalkan. Sesi tersimpan di checkpoint.'})
        setTimeout(() => gwRef.current?.start(), 50)
      } else {
        gwRef.current?.stop()
        exit()
      }
      return
    }
    if (key.escape) {
      setShowHelp(false)
      return
    }
    if (key.pageDown) {
      dispatch({type: 'scroll', delta: -Math.max(1, Math.floor(rows / 2))})
      return
    }
    if (key.pageUp) {
      dispatch({type: 'scroll', delta: Math.max(1, Math.floor(rows / 2))})
      return
    }
    // riwayat input
    if (key.upArrow) {
      if (history.length === 0) return
      const idx = histIdx.current === -1 ? history.length - 1 : Math.max(0, histIdx.current - 1)
      histIdx.current = idx
      setDraft(history[idx])
      return
    }
    if (key.downArrow) {
      if (histIdx.current === -1) return
      const idx = histIdx.current + 1
      if (idx >= history.length) {
        histIdx.current = -1
        setDraft('')
      } else {
        histIdx.current = idx
        setDraft(history[idx])
      }
      return
    }
  })

  const cyberPhase = state.lastState?.phase ?? null
  const evidence = state.lastState?.evidence?.length ?? 0
  const hypotheses = state.lastState?.hypotheses?.length ?? 0
  const attempts = state.lastState?.attempts?.length ?? 0
  const flags = state.lastState?.flags?.length ?? 0

  // Rakit daftar item untuk log statis (append-only). Setiap item adalah
  // satu "kartu" yang dicetak permanen di atas region live.
  type LogItem = {id: string; node: React.ReactNode}
  const logItems: LogItem[] = [{id: 'intro', node: (
    <Box flexDirection="column">
      <Banner cols={cols} rows={rows} />
      <SessionPanel
        cols={cols}
        rows={rows}
        info={state.info}
        sessionId={state.sessionId}
        phase={cyberPhase}
        toolsCount={3}
        cwd={projectRoot}
      />
      <Box height={1} />
    </Box>
  )}]

  for (const l of state.lines) {
    logItems.push({id: `line-${l.id}`, node: <TranscriptLineView line={l} width={cols - 2} />})
  }

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Log historis: banner + transkrip, append-only, stabil. */}
      <Static items={logItems}>
        {(item) => <Box key={item.id}>{item.node}</Box>}
      </Static>

      {/* Region live: aktivitas berjalan, panel state, help, status, composer. */}
      {state.activity.length > 0 && (
        <ActivityBlock
          title="Aktivitas agen"
          items={state.activity.slice(-12)}
          width={cols - 4}
          active={state.phase === 'busy'}
        />
      )}

      {state.showStatePanel && <StatePanel state={state.lastState} cols={cols} />}

      {showHelp && (
        <Box marginY={1}>
          <HelpOverlay cols={cols} />
        </Box>
      )}

      <StatusBar
        phase={state.phase}
        busySince={state.busySince}
        cyberPhase={cyberPhase}
        evidence={evidence}
        hypotheses={hypotheses}
        attempts={attempts}
        flags={flags}
        sessionId={state.sessionId}
        verbSeed={state.busyVerbSeed}
        cols={cols - 2}
      />

      {state.notice && (
        <Box paddingX={1}>
          <Text color={hex('warn')}>{state.notice}</Text>
        </Box>
      )}
      {state.fatal && (
        <Box paddingX={1}>
          <Text color={hex('error')}>✕ {state.fatal}</Text>
        </Box>
      )}

      <Composer phase={state.phase} value={draft} onChange={setDraft} onSubmit={onSubmit} />
      <Box paddingX={1}>
        <Text color={hex('muted')}>
          Enter kirim · /help · /status · ↑/↓ riwayat · PgUp/PgDn scroll · Ctrl+C{' '}
          {state.phase === 'busy' ? 'batalkan' : 'keluar'}
        </Text>
      </Box>
    </Box>
  )
}

/** Satu baris transkrip di log statis. */
function TranscriptLineView({line, width}: {line: import('./state/appStore.ts').TranscriptLine; width: number}) {
  const meta: Record<string, {label: string; color: string}> = {
    user: {label: 'kamu', color: hex('tool')},
    agent: {label: 'fenrys', color: hex('accent')},
    system: {label: 'sys', color: hex('muted')},
    error: {label: 'error', color: hex('error')},
  }
  const m = meta[line.role] ?? meta.system
  return (
    <Box>
      <Text color={m.color} bold>
        {m.label} ›{' '}
      </Text>
      <Text wrap="wrap">{line.text}</Text>
    </Box>
  )
}
