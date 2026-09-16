/** Kata kerja ambient & charm — nada "perburuan serigala", Bahasa Indonesia. */

export const BUSY_VERBS = [
  'memburu',
  'mengendus jejak',
  'mengintai target',
  'menyusuri jaringan',
  'membedah layanan',
  'menelisik bukti',
  'menguji hipotesis',
  'memetakan permukaan',
  'menggali lebih dalam',
  'mengunci target',
] as const

export const THINK_VERBS = [
  'merenung',
  'menimbang',
  'menyusun rencana',
  'membaca situasi',
  'menghubungkan titik',
] as const

export const LONG_RUN_CHARMS = [
  'masih melacak…',
  'mengasah cakar…',
  'mengendus lebih tajam…',
  'berkeliling memastikan…',
  'menunggu celah terbuka…',
] as const

export const IDLE_FACES = ['(・ω・)', '(˶ᵔᵕᵔ˶)', '(¬‿¬)', '(ᵕ—ᴗ—)'] as const

export function pick<T>(arr: readonly T[], seed: number): T {
  return arr[Math.abs(seed) % arr.length]
}
