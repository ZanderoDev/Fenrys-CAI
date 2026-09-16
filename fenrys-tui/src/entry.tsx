import React from 'react'
import {render} from 'ink'
import {App} from './app.tsx'

// Paksa deteksi warna maksimal sedini mungkin (sebelum render pertama).
if (!process.env.FORCE_COLOR && process.stdout.isTTY) {
  process.env.FORCE_COLOR = '3'
}

if (!process.stdin.isTTY) {
  console.error('FENRYS-CAI TUI memerlukan terminal interaktif (TTY).')
  process.exit(1)
}

const {waitUntilExit} = render(<App />, {exitOnCtrlC: false})

waitUntilExit().then(() => {
  // beri napas agar escape sequence terminal bersih
  process.stdout.write('')
})
