# PRD - Aplikasi Procurement

Versi: 1.0 | Tanggal: 24 Okt 2026 | Deadline submit: 25 Okt 2026 23:59:59

## 1. Ringkasan
Aplikasi web untuk menangani tahapan pengadaan dari **permintaan (Purchase Request)** sampai **barang/jasa diterima di gudang (Goods Receipt)**. Aplikasi ini mendigitalkan alur PR -> approval -> RFQ -> penawaran vendor -> pemilihan vendor -> PO -> penerimaan barang, lengkap dengan jejak audit.

## 2. Masalah yang Diselesaikan
- Permintaan pengadaan tersebar (chat/email/kertas), sulit dilacak statusnya.
- Tidak ada pembanding penawaran vendor yang terstruktur.
- Approval tidak terdokumentasi, tidak ada audit trail.
- Tidak ada kaitan jelas antara PR, PO, dan barang yang benar-benar diterima.

## 3. Tujuan
1. Seluruh alur pengadaan dapat dijalankan end-to-end dalam satu aplikasi.
2. Setiap dokumen punya status yang jelas dan dapat dilacak.
3. Setiap perubahan status tercatat (siapa, kapan, apa).
4. Perbandingan penawaran vendor transparan.
5. (Nilai plus) Input penawaran vendor dipercepat dengan AI/Computer Vision.

## 4. Scope
### In Scope
- Master data: user, department, item, vendor
- Purchase Request (PR) + approval
- RFQ ke beberapa vendor
- Input penawaran vendor + perbandingan + pemilihan
- Purchase Order (PO) + approval manager
- Goods Receipt (pencatatan penerimaan, mendukung partial)
- Audit log, dashboard sederhana
- AI extractor penawaran (opsional)

### Out of Scope (TIDAK BOLEH dibuat)
- Aplikasi gudang (stok, mutasi, lokasi rak, inventory)
- Aplikasi pembayaran (invoice, payment, 3-way matching pembayaran)
- Portal login vendor (vendor hanya lane di BPMN; data penawaran diinput oleh Procurement Officer)

## 5. User Role
| Role | Deskripsi | Akses utama |
|---|---|---|
| Admin | Kelola master data dan user | Semua master data |
| Requester | Staff pembuat permintaan | Buat/lihat PR milik sendiri |
| Dept Head | Atasan departemen | Approve/reject PR departemennya |
| Procurement Officer | Eksekutor pengadaan | Review PR, RFQ, quotation, evaluasi, buat PO |
| Procurement Manager | Pemberi persetujuan akhir | Approve vendor terpilih dan PO |
| Warehouse Receiver | Penerima barang | Buat Goods Receipt |
| Vendor (lane BPMN saja) | Pihak eksternal | Tidak login |

## 6. Fitur dan Prioritas
Prioritas: P0 wajib, P1 penting, P2 nilai plus.

| ID | Fitur | Role | Prioritas |
|---|---|---|---|
| F-01 | Login, logout, role-based access | Semua | P0 |
| F-02 | CRUD department, item, vendor, user | Admin | P0 |
| F-03 | Buat/edit/submit PR (multi item) | Requester | P0 |
| F-04 | Approve/reject PR + catatan | Dept Head | P0 |
| F-05 | Review PR, tandai masuk sourcing | Proc. Officer | P0 |
| F-06 | Buat RFQ dari PR, pilih beberapa vendor | Proc. Officer | P0 |
| F-07 | Input penawaran per vendor (per item) | Proc. Officer | P0 |
| F-08 | Tabel perbandingan penawaran + pilih vendor | Proc. Officer | P0 |
| F-09 | Approve/reject vendor terpilih dan PO | Proc. Manager | P0 |
| F-10 | Terbit PO dari quotation terpilih | Proc. Officer | P0 |
| F-11 | Goods Receipt (partial/full) | Warehouse Receiver | P0 |
| F-12 | Audit log perubahan status | Sistem | P0 |
| F-13 | Dashboard ringkasan status | Semua | P1 |
| F-14 | Cetak/ekspor PO (PDF/print view) | Proc. Officer | P1 |
| F-15 | Filter, pencarian, pagination daftar dokumen | Semua | P1 |
| F-16 | AI extractor penawaran dari foto/PDF | Proc. Officer | P2 |

## 7. User Story (ringkas)
- Sebagai **Requester**, saya ingin membuat PR berisi beberapa item agar kebutuhan saya diproses.
- Sebagai **Dept Head**, saya ingin approve/reject PR beserta alasan agar anggaran terkontrol.
- Sebagai **Procurement Officer**, saya ingin membandingkan penawaran beberapa vendor agar memilih yang terbaik.
- Sebagai **Procurement Manager**, saya ingin menyetujui PO agar pembelian sah.
- Sebagai **Warehouse Receiver**, saya ingin mencatat barang yang datang (termasuk sebagian) agar status PO akurat.
- Sebagai **Procurement Officer**, saya ingin upload penawaran vendor dan form terisi otomatis agar hemat waktu.

## 8. Acceptance Criteria Utama
1. PR hanya bisa diedit saat `DRAFT`; setelah submit hanya bisa dilihat.
2. Requester tidak dapat meng-approve PR miliknya sendiri.
3. RFQ minimal 1 vendor; perbandingan tampil jika minimal 1 quotation masuk.
4. PO hanya dapat terbit dari quotation berstatus `SELECTED` yang sudah di-approve Manager.
5. Goods Receipt tidak boleh melebihi sisa qty PO; partial receipt mengubah PO menjadi `PARTIALLY_RECEIVED`.
6. Setiap perubahan status menghasilkan satu baris AuditLog.
7. Fitur AI gagal/tidak tersedia -> input manual tetap berfungsi.

## 9. Metrik Keberhasilan (untuk penilaian tes)
- Alur happy path end-to-end berjalan tanpa error.
- Skenario PR ditolak dan partial receipt berjalan.
- Schema database rapi, ternormalisasi, ada constraint.
- Kode terstruktur (service layer, tanpa logika bisnis di view).
- Konsisten dengan BPMN dan WBS.

## 10. Asumsi
- Satu mata uang (IDR).
- Approval PR satu level (Dept Head), approval PO satu level (Proc. Manager).
- Vendor tidak login; komunikasi RFQ/PO ke vendor dilakukan di luar sistem (sistem hanya mencatat status "sent").
