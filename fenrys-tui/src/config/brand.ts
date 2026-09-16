/** Identitas merek Fenrys — satu-satunya sumber nama/tagline di TUI. */

export const BRAND = {
  name: 'FENRYS-CAI',
  icon: '🐺',
  prompt: '❯',
  welcome: 'Ketik objektif CTF/lab kamu, atau /help untuk melihat perintah.',
  goodbye: 'Sampai jumpa di perburuan berikutnya. 🐺',
  helpHeader: 'Perintah Fenrys',
  tool: '┊',
} as const

export const TAGLINES = {
  full: 'Autonomous Cyber Agent · CTF / HTB / Authorized Lab',
  mid: 'Autonomous Cyber Agent',
  tiny: BRAND.name,
} as const

export const VERSION = '0.2.0'
