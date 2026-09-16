/**
 * ASCII art Fenrys — logo figlet "FENRYS" + hero serigala melolong.
 * Pewarnaan memakai gradient per-baris (primary -> accent -> border -> muted).
 */
import {ink} from './theme.ts'

/* ------------------------------------------------------------------ */
/* LOGO "FENRYS" (ANSI Shadow, 6 baris x 56 kolom)                     */
/* ------------------------------------------------------------------ */
export const LOGO_ART: string[] = [
  '███████╗███████╗███╗   ██╗██████╗ ██╗   ██╗███████╗',
  '██╔════╝██╔════╝████╗  ██║██╔══██╗╚██╗ ██╔╝██╔════╝',
  '█████╗  █████╗  ██╔██╗ ██║██████╔╝ ╚████╔╝ ███████╗',
  '██╔══╝  ██╔══╝  ██║╚██╗██║██╔══██╗  ╚██╔╝  ╚════██║',
  '██║     ███████╗██║ ╚████║██║  ██║   ██║   ███████║',
  '╚═╝     ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝   ╚═╝   ╚══════╝',
]
export const LOGO_WIDTH = 56

/* ------------------------------------------------------------------ */
/* HERO SERIGALA MELOLONG — besar, 33 baris x 56-63 kolom              */
/* ------------------------------------------------------------------ */
export const WOLF_ART: string[] = [
  '                              /\\',
  '                             /  \\          __',
  '                            / /\\ \\      .d$$b',
  '                           / /  \\ \\   .\' TO$;\\',
  '                          / / /\\ \\ \\ /  : TP._;',
  '                         / / /  \\ \\ / _.;  :Tb|',
  '                        / / /    \\ X   /   ;j$j',
  '                       / / /  /\\  / \\-"      d$$$$',
  '                      / / /  /  \\/  .\' ..     d$$$$;',
  '                     / / /  /    \\ /  /P\'    d$$$$P. |\\',
  '                    / / /  / /\\  \\/   "     .d$$$P\' |\\^"l',
  '                   / / /  / /  \\  .\'         `T$P^"""""  :',
  '                  / / /  / / /\\ \\_.\'      _.\'            ;',
  '                 / / /  / / /  \\-.-".-\'-\' ._.     _.-"  .-"',
  '                / / /  / / / /\\ \\".-" _____  ._         .-"',
  '               / / /  / / / /  \\-(.g$$$$$$$b.          .\'',
  '              / / /  / / / / /\\ \\  ""^^T$$$P^)        .(:',
  '             / / /  / / / / /  \\ \\   _/  -"  /.\'     /:/;',
  '            / / /  / / / / / /\\ \\ ._.\'-\'`-\'  ")/     /;/;',
  '           / / /  / / / / / /  \\ `-.-"..--""   " /    /  ;',
  '          / / /  / / / / / / /\\ \\-" ..--""       -\'     :',
  '         / / /  / / / / / / /  ..--""--.-"        (\\   .-(\\',
  '        / / /  / / / / / / /\\ \\  ..--""            `-\\(\\/;`',
  '       / / /  / / / / / / /  \\ \\   _.                  :',
  '      / / /  / / / / / / / /\\ \\ \\                     ;`-',
  '     / / /  / / / / / / / /  \\ \\ \\                    :',
  '    / / /  / / / / / / / / /\\ \\ \\ \\                   ;',
  '   / / /  / / / / / / / / /  \\_\\_\\_\\                 /',
  '  /_/_/  /_/_/_/_/_/_/_/_/    (______)              /',
  ' (_)___)(_/_/_/_/_/_/_/_/                          /',
  '   \\|__\\|  \\|__\\|__\\|/                          /',
  '    "----"   "--------"                        /',
  '                                              /',
]
export const WOLF_WIDTH = 59
export const WOLF_HEIGHT = WOLF_ART.length

/* Hero sedang (~13 baris) untuk terminal pendek. */
export const WOLF_ART_MID: string[] = [
  '      /\\',
  '     /  \\      __',
  '    / /\\ \\  .d$$b',
  '   / /  \\ \\\' TO$;\\',
  '  / / /\\ \\ V  TP._;',
  ' / / /  \\ _.; :Tb|',
  ' \\ \\ \\ /\\  / ;j$j',
  '  \\ \\ \\/  \\"-" d$$',
  '   \\ \\ /\\ \\/P\'d$$P.',
  '    \\ \\/  \\  d$$P\'',
  '     \\__/\\__`T$P^"',
  '        "----"',
]
export const WOLF_MID_WIDTH = 22

/* ------------------------------------------------------------------ */
/* Pewarnaan gradient per-baris                                        */
/* ------------------------------------------------------------------ */
const PALETTE = [ink.primary, ink.accent, ink.border, ink.muted]

function grade(art: string[], mapFn: (i: number, rows: number) => number): string[] {
  const rows = art.length
  return art.map((text, i) => {
    const g = Math.max(0, Math.min(3, mapFn(i, rows)))
    return (PALETTE[g] ?? ink.muted)(text)
  })
}

/** Logo FENRYS: 2 baris primary, 2 accent, 1 border, 1 muted. */
export function logoColored(): string[] {
  const seq = [0, 0, 1, 1, 2, 3]
  return LOGO_ART.map((text, i) => (PALETTE[seq[i] ?? 3] ?? ink.muted)(text))
}

/** Hero serigala besar: gradient halus atas->bawah. */
export function wolfColored(): string[] {
  return grade(WOLF_ART, (i, rows) => Math.floor((i / Math.max(1, rows - 1)) * 4))
}

/** Hero sedang. */
export function wolfMidColored(): string[] {
  return grade(WOLF_ART_MID, (i, rows) => Math.floor((i / Math.max(1, rows - 1)) * 4))
}
