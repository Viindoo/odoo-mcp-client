# Odoo Semantic — Panduan Konsultan

> **Mulai cepat (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` → `claude plugin install odoo-semantic@viindoo-plugins` → `/odoo-semantic:connect`. Detail + AI tools lainnya: [client setup](../../setup.md).

Untuk konsultan fungsional dan solution architect: verifikasi ketersediaan fitur dengan cepat, selesaikan gap analysis, dan tentukan ruang lingkup kustomisasi sebelum mengunci estimasi.

---

## Masalah yang Diselesaikan Tool Ini untuk Konsultan

Pain point yang paling sering dihadapi konsultan:

- **"Does Odoo do X natively?"** — cek dulu sebelum menjanjikannya ke klien
- **"Is this CE or EE?"** — hindari temuan yang memalukan di tengah proyek
- **"How hard is this customization?"** — pahami inheritance chain sebelum membuat estimasi
- **"Show me an existing example"** — tunjukkan kapabilitas tanpa membangun demo dari nol

---

## Tool yang Paling Berguna untuk Konsultan

| Tool | Yang dijawab |
|------|--------------|
| `check_module_exists` | Apakah fitur ini native? CE atau EE? Mulai versi berapa fitur ini ditambahkan? |
| `find_examples` | Tampilkan kode Odoo nyata yang melakukan hal serupa |
| `lookup_core_api` | Apakah API ini tersedia dan stabil? |
| `resolve_model` | Seberapa kompleks model ini? Berapa banyak modul yang sudah memperluasnya? |
| `impact_analysis` | Seberapa berisiko kustomisasi yang diminta klien? |
| `api_version_diff` | Apa yang berubah antara versi klien saat ini dan target upgrade? |

---

## Workflow Feature Gap Analysis

### 1. Cek ketersediaan native terlebih dahulu

```
check_module_exists("account_budget", "17.0")
```

Hasil ini memberi tahu Anda: modul tersedia atau tidak, CE vs EE, dan apakah ada risiko kebingungan EE (addon gratis dengan nama mirip yang bisa menyesatkan).

### 2. Cari contoh yang sebanding

```
find_examples("budget control with approval workflow and department-level limits")
```

Semantic search di seluruh repo terindeks — mengembalikan cuplikan kode nyata dari codebase yang sesuai dengan deskripsi Anda.

### 3. Pahami kompleksitas model

```
resolve_model("account.budget", "17.0")
```

Jumlah field, ekstensi modul, daftar method. Jika model diperluas oleh 15+ modul, risiko kustomisasi lebih tinggi — masukkan faktor itu ke estimasi Anda.

### 4. Cek jalur upgrade jika relevan

```
api_version_diff("account.move", "16.0", "17.0")
```

Temukan breaking changes dengan cepat sebelum memberi tahu klien seberapa mulus upgrade akan berjalan.

---

## Contoh Pertanyaan Konsultan

Salin prompt ini ke AI tool Anda:

1. **Cek ketersediaan fitur:**
   > "Using odoo-semantic, does Odoo 17.0 have a native field service management module? Is it Community or Enterprise?"

2. **Gap analysis untuk prospek:**
   > "Using odoo-semantic, check if Odoo 17.0 Community has a subscription / recurring invoice module. If EE-only, what are the key features missing from CE?"

3. **Ruang lingkup kustomisasi:**
   > "Using odoo-semantic, resolve model account.move in Odoo 17.0. How many modules extend it? Does extending it for invoice approval carry HIGH risk?"

4. **Persiapan demo berbasis contoh:**
   > "Using odoo-semantic, find_examples for approval workflow on sale.order with multi-level validation. Show me real code from indexed repos."

5. **Ringkasan risiko upgrade:**
   > "Using odoo-semantic, find_deprecated_usage for Odoo 17.0. My client is on 16.0. What are the top 3 risks they should budget for?"

---

## Plugin Skills (Claude Code)

Jika Anda menggunakan **Claude Code** dengan plugin Odoo Semantic:

| Skill | Fungsinya |
|-------|-----------|
| `/odoo-feature-check` | Laporan lengkap ketersediaan fitur: native vs EE vs addon; termasuk flag CE/EE |
| `/odoo-gap-analysis` | Gap analysis antara kebutuhan klien dan fitur native Odoo; menandai kemampuan CE yang belum tersedia |

---

## Membaca Hasil

- **`is_ee_confusion: true`** — Ada modul CE yang dikenal memiliki nama mirip; klien sering tertukar antara CE dan EE. Tandai ini di proposal Anda.
- **`Fields: N`** — Model memiliki N field di seluruh modul yang memperluasnya. Semakin banyak field = semakin tinggi kompleksitas.
- **`Extends: N modules`** — N modul menyentuh model ini. Risiko custom extension meningkat seiring jumlah N.
- **`status: deprecated`** dari `lookup_core_api` — API yang menjadi dasar kustomisasi Anda sedang dihapus. Ini adalah risiko proyek.

---

## Membuat Estimasi dari Hasil

| Signal | Implikasi |
|--------|-----------|
| Model extended by >10 modules | Kustomisasi berisiko menengah hingga tinggi — rencanakan testing ekstra |
| impact_analysis: Risk HIGH | Anggarkan 2-3x estimasi dev; perubahan ini akan berdampak ke banyak hal |
| check_module_exists: EE only | Tambahkan biaya lisensi ke proposal |
| find_deprecated_usage: 3+ items | Proyek upgrade membutuhkan fase remediasi |
