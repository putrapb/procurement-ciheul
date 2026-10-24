# Design.md - UI/UX

Prinsip: **fungsional, konsisten, cepat dibangun.** Tanpa build step frontend. Penilaian fokus ke alur dan kerapian, bukan visual mewah.

## 1. Stack UI
- Django Templates (base layout + partials)
- Bootstrap 5 via CDN
- HTMX untuk interaksi ringan (filter tabel, tambah baris item, modal approve/reject)
- Bahasa antarmuka: Indonesia

## 2. Design Tokens
| Token | Nilai |
|---|---|
| Primary | `#0d6efd` (Bootstrap default) |
| Success / Warning / Danger | `#198754` / `#ffc107` / `#dc3545` |
| Font | System UI stack |
| Spacing | Skala Bootstrap (`p-2`, `p-3`, `gap-3`) |
| Radius | Default Bootstrap |

### Badge Status (konsisten di seluruh halaman)
| Status | Warna |
|---|---|
| DRAFT | secondary |
| SUBMITTED / PENDING_APPROVAL | warning |
| APPROVED / SELECTED | info |
| IN_SOURCING / SENT | primary |
| PARTIALLY_RECEIVED | warning (outline) |
| COMPLETED | success |
| REJECTED / CANCELLED | danger / dark |

## 3. Layout Global
```
+-----------------------------------------------+
| Navbar: logo | menu sesuai role | user | logout |
+-----------+-----------------------------------+
| Sidebar   |  Breadcrumb                       |
| (menu)    |  Judul halaman     [Tombol aksi]  |
|           |  Konten (kartu / tabel / form)    |
+-----------+-----------------------------------+
```
Menu hanya menampilkan item yang boleh diakses role aktif.

## 4. Peta Halaman per Role
| Role | Halaman |
|---|---|
| Semua | Login, Dashboard, Profil |
| Admin | Departemen, Item, Vendor, User |
| Requester | Daftar PR saya, Buat PR, Detail PR |
| Dept Head | Antrean approval PR, Detail PR (aksi approve/reject) |
| Officer | PR siap sourcing, Daftar RFQ, Detail RFQ, Input Quotation, Perbandingan, Daftar PO, Detail PO |
| Manager | Antrean approval (vendor dan PO) |
| Warehouse Receiver | Daftar PO siap terima, Form GR |

## 5. Layar Kunci

### 5.1 Dashboard
- Kartu ringkasan: jumlah dokumen per status (sesuai role)
- Tabel "Perlu tindakan saya" (antrean tugas)

### 5.2 Form PR
- Header: departemen (otomatis), tanggal dibutuhkan, alasan
- Tabel item dinamis (HTMX tambah/hapus baris): item, qty, catatan
- Tombol: Simpan Draft, Submit

### 5.3 Detail Dokumen (pola sama untuk PR/RFQ/PO)
- Kartu header: nomor, status (badge), pembuat, tanggal
- Tab: **Item**, **Approval**, **Riwayat (audit log)**
- Tombol aksi kontekstual sesuai role dan status (disembunyikan jika tidak berhak)

### 5.4 Perbandingan Penawaran
```
| Item   | Qty | Vendor A | Vendor B | Vendor C |
| Laptop |  5  | 12.0jt * | 12.5jt   | 11.8jt   |
| Total  |     | 60.0jt   | 62.5jt   | 59.0jt v |
| Lead time        | 7 hari | 5 hari | 10 hari |
[ Pilih vendor ]  (justifikasi wajib bila bukan termurah)
```
Sel harga terendah per baris diberi highlight hijau.

### 5.5 Approve / Reject
Modal: textarea catatan (wajib saat reject), tombol Setuju / Tolak.

### 5.6 Goods Receipt
Tabel item PO: qty dipesan, sudah diterima, **sisa**, input qty diterima (max = sisa), kondisi. Validasi sisi klien dan server.

### 5.7 Upload Penawaran (AI, opsional)
Dropzone file -> tombol "Ekstrak dengan AI" -> form quotation terisi (ditandai "hasil AI, mohon periksa") -> user koreksi -> simpan. Link "Isi manual" selalu tersedia.

## 6. Pola Interaksi dan Umpan Balik
- Pesan sukses/error via Django messages (alert Bootstrap).
- Error validasi tampil di bawah field.
- Aksi destruktif/final meminta konfirmasi.
- Tabel daftar: filter status, pencarian nomor, pagination 20/halaman.
- Empty state: teks penjelas + tombol aksi utama.

## 7. Aksesibilitas Dasar
Label pada semua input, kontras warna bawaan Bootstrap, status tidak hanya dibedakan lewat warna (ada teks pada badge).

## 8. Struktur Template
```
templates/
├── base.html
├── partials/ (navbar, sidebar, messages, status_badge, pagination)
├── accounts/ masterdata/ requisitions/ sourcing/ orders/ receiving/
└── dashboard.html
```
