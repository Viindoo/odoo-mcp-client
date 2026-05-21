# Odoo Semantic — Panduan Konsultan

> **Mulai (Claude Code):** `claude plugin marketplace add Viindoo/claude-plugins` → `claude plugin install odoo-semantic@viindoo-plugins` → `/odoo-semantic:connect`. Detail + AI tools lainnya: [client setup](../setup.md).

Untuk konsultan fungsional dan arsitek solusi: verifikasi ketersediaan fitur dengan cepat, selesaikan analisis kesenjangan (gap analysis), dan tentukan cakupan kustomisasi sebelum memberikan estimasi.

---

## Masalah yang Diselesaikan untuk Konsultan

Poin-poin masalah konsultan yang paling umum:

- **"Apakah Odoo mendukung X secara native?"** — periksa sebelum menjanjikannya ke klien
- **"Ini CE atau EE?"** — hindari penemuan yang memalukan di tengah proyek
- **"Seberapa sulit kustomisasi ini?"** — pahami rantai inheritance sebelum estimasi
- **"Tunjukkan contoh yang sudah ada"** — demonstrasikan kemampuan tanpa membangun demo dari nol

---

## Tools Paling Berguna untuk Konsultan

| Tool | Apa yang dijawab |
|------|----------------|
| `check_module_exists` | Apakah fitur ini native? CE atau EE? Versi berapa yang menambahkannya? |
| `find_examples` | Tunjukkan kode Odoo asli yang melakukan sesuatu yang serupa |
| `lookup_core_api` | Apakah API ini ada dan stabil? |
| `resolve_model` | Seberapa kompleks model ini? Berapa banyak modul yang sudah memperluasnya? |
| `impact_analysis` | Seberapa berisiko kustomisasi yang diinginkan klien? |
| `api_version_diff` | Apa yang berubah antara versi saat ini klien dan target upgrade? |

---

## Alur Kerja Analisis Kesenjangan Fitur

### 1. Periksa ketersediaan native terlebih dahulu

```
check_module_exists("account_budget", "17.0")
```

Ini memberi tahu Anda: modul ada (ya/tidak), CE vs EE, dan apakah ada risiko kebingungan EE (addon gratis dengan nama serupa yang mungkin menyesatkan).

### 2. Temukan contoh yang sebanding

```
find_examples("budget control with approval workflow and department-level limits")
```

Pencarian semantik di seluruh repositori yang diindeks — mengembalikan cuplikan kode asli dari codebase yang sesuai dengan yang Anda deskripsikan.

### 3. Pahami kompleksitas model

```
resolve_model("account.budget", "17.0")
```

Jumlah field, ekstensi modul, daftar method. Jika model memiliki 15+ modul yang memperluasnya, risiko kustomisasi lebih tinggi — pertimbangkan itu dalam estimasi Anda.

### 4. Periksa jalur upgrade jika relevan

```
api_version_diff("account.move", "16.0", "17.0")
```

Cepat identifikasi perubahan yang merusak (breaking changes) sebelum memberi tahu klien seberapa lancar upgrade akan terjadi.

---

## Contoh Pertanyaan Konsultan

Salin prompt ini ke AI tool Anda:

1. **Pengecekan ketersediaan fitur:**
   > "Menggunakan odoo-semantic, apakah Odoo 17.0 memiliki modul manajemen field service secara native? Apakah Community atau Enterprise?"

2. **Analisis kesenjangan untuk prospek:**
   > "Menggunakan odoo-semantic, periksa apakah Odoo 17.0 Community memiliki modul langganan / invoice berulang. Jika hanya EE, apa fitur utama yang hilang dari CE?"

3. **Cakupan kustomisasi:**
   > "Menggunakan odoo-semantic, resolve model account.move di Odoo 17.0. Berapa banyak modul yang memperluasnya? Apakah memperluasnya untuk persetujuan invoice membawa risiko TINGGI?"

4. **Persiapan demo berbasis contoh:**
   > "Menggunakan odoo-semantic, find_examples untuk approval workflow pada sale.order dengan validasi multi-level. Tunjukkan kode asli dari repositori terindeks."

5. **Ringkasan risiko upgrade:**
   > "Menggunakan odoo-semantic, find_deprecated_usage untuk Odoo 17.0. Klien saya ada di versi 16.0. Apa 3 risiko teratas yang harus mereka persiapkan?"

---

## Plugin Skills (Claude Code)

Jika Anda menggunakan **Claude Code** dengan plugin Odoo Semantic:

| Skill | Apa yang dilakukan |
|-------|-------------|
| `/odoo-feature-check` | Laporan ketersediaan fitur lengkap: native vs EE vs addon; termasuk flag CE/EE |
| `/odoo-gap-analysis` | Analisis kesenjangan antara kebutuhan klien dan fitur native Odoo; menandai kemampuan CE yang hilang |

---

## Membaca Hasil

- **`is_ee_confusion: true`** — Ada modul CE dengan nama serupa yang sudah diketahui; klien sering membingungkan CE dan EE. Tandai ini dalam proposal Anda.
- **`Fields: N`** — Model memiliki N field di semua modul yang memperluasnya. Lebih banyak field = kompleksitas lebih tinggi.
- **`Extends: N modules`** — N modul menyentuh model ini. Risiko ekstensi kustom meningkat seiring N.
- **`status: deprecated`** dari `lookup_core_api` — API yang menjadi dasar kustomisasi Anda sedang dihapus. Ini adalah risiko proyek.

---

## Estimasi dari Hasil

| Sinyal | Implikasi |
|--------|-------------|
| Model diperluas oleh >10 modul | Kustomisasi berisiko sedang-tinggi — rencanakan pengujian tambahan |
| impact_analysis: Risk HIGH | Siapkan anggaran 2-3x estimasi dev; ini akan merusak hal-hal |
| check_module_exists: EE only | Tambahkan biaya lisensi ke proposal |
| find_deprecated_usage: 3+ item | Proyek upgrade membutuhkan fase remediasi |