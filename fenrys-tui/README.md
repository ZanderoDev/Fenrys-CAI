# 🐺 FENRYS-CAI — Terminal UI

Terminal-first TUI untuk **FENRYS-CAI**, agen siber autonomous untuk CTF / HTB /
authorized lab. Dibangun dengan **Ink + React 19**, berbicara ke inti Python
lewat **newline-delimited JSON-RPC** via stdio — tanpa mengubah satu baris pun
logika inti.

## Menjalankan

```bash
cd ~/Dokumen/claude
source .venv/bin/activate        # agar provider LLM & gateway resolve
cd fenrys-tui
npm start
```

TUI men-spawn `python -m fenrys_cai.tui.entry` dari **root proyek** dan berkomunikasi
lewat NDJSON di stdio.

## Konfigurasi provider

Diwarisi dari environment (dibaca gateway Python):

```bash
export FENRYS_LLM_ENDPOINT="https://api.anthropic.com"   # atau OpenAI-compatible
export FENRYS_LLM_API_KEY="sk-..."
export FENRYS_LLM_MODEL="claude-sonnet-4-20250514"
export FENRYS_LLM_PROTOCOL="anthropic"                    # atau "openai"
```

Jika provider belum siap, panel sesi akan menampilkan peringatan dan cara mengisinya.

## Fitur

- **Banner serigala responsif** — logo figlet FENRYS + hero serigala melolong
  33 baris (4 tier: full / medium / compact / tiny sesuai ukuran terminal).
- **Panel sesi** — status provider, jumlah tools, session id, fase, cwd.
- **Status bar hidup** — spinner braille + kata-kerja perburuan yang berganti,
  elapsed time, fase, dan hitungan evidence/hipotesis/attempt/flags.
- **Activity tree** — rails `├─/└─` untuk reasoning, tool (✓/✗/⚠), specialist,
  dan verifikasi, dengan status berwarna. Anti-loop ditandai jelas.
- **Slash commands + multi-session**:
  - `/help` — bantuan
  - `/new [nama]` — sesi baru
  - `/session <id>` — pindah sesi (lanjut dari checkpoint)
  - `/resume [id]` — lanjutkan sesi dari checkpoint
  - `/sessions` — daftar sesi
  - `/status` — toggle panel state (flags/hosts/services/hipotesis/dead-ends)
  - `/clear` — bersihkan layar
  - `/exit` — keluar
- **Riwayat input** — ↑/↓ menelusuri perintah sebelumnya.
- **Pembatalan aman** — Ctrl+C saat agen bekerja membatalkan turn
  (kill + respawn gateway; state sesi tetap aman di checkpoint SQLite).

## Arsitektur

```
fenrys-tui/src/
├── entry.tsx            # TTY gate + render
├── app.tsx              # komposisi top-level + wiring gateway/store/slash
├── gatewayClient.ts     # spawn python + NDJSON demux + recovery
├── types.ts             # kontrak wire (persis seperti yang di-emit core)
├── theme.ts / banner.ts # palet "serigala malam" + ASCII art
├── config/              # brand, kata-kerja ambient
├── state/appStore.ts    # reducer murni: event gateway -> state UI
├── domain/              # session registry (read-only), util teks/komposisi
├── components/          # Banner, SessionPanel, StatusBar, Composer,
│                        #   Transcript, ActivityTree, StatePanel, overlays
└── slash/registry.ts    # perintah slash lokal
```

**Batas tegas:** TypeScript memiliki layar; Python memiliki sesi, tools, dan
panggilan model. Tidak ada logika agen di renderer.

## Pengembangan

```bash
npm run build   # typecheck (tsc --noEmit)
```
