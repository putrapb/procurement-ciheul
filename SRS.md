# SRS - Software Requirements Specification

Versi: 1.0 | Rujukan: PRD.md (F-xx), WBS.xlsx, BPMN.pdf

## 1. Pendahuluan
Dokumen ini merinci kebutuhan fungsional dan non-fungsional Aplikasi Procurement. Setiap requirement ditautkan ke fitur PRD (F-xx) agar konsisten dengan WBS dan BPMN.

## 2. Definisi
| Istilah | Arti |
|---|---|
| PR | Purchase Request, permintaan pengadaan |
| RFQ | Request for Quotation, permintaan penawaran ke vendor |
| PO | Purchase Order |
| GR | Goods Receipt, catatan penerimaan barang |

## 3. Functional Requirements

### 3.1 Auth dan Akses (F-01)
- FR-001: Sistem menyediakan login/logout berbasis username dan password.
- FR-002: Setiap user memiliki tepat satu role.
- FR-003: Setiap view dibatasi role; akses tidak sah menghasilkan HTTP 403.

### 3.2 Master Data (F-02)
- FR-010: Admin dapat CRUD Department, Item (kode unik, nama, satuan), Vendor (kode unik, kontak), User.
- FR-011: Master data yang sudah dipakai dokumen tidak dapat dihapus (gunakan `is_active=False`).

### 3.3 Purchase Request (F-03, F-04, F-05)
- FR-020: Requester membuat PR dengan nomor otomatis `PR-YYYYMM-NNNN`, departemen, tanggal dibutuhkan, alasan, dan >= 1 item (item, qty > 0, catatan).
- FR-021: PR status `DRAFT` dapat diedit/dihapus oleh pembuatnya.
- FR-022: Submit mengubah status ke `SUBMITTED` dan membuat Approval `PENDING` untuk Dept Head departemen terkait.
- FR-023: Dept Head dapat `APPROVE` atau `REJECT` (alasan wajib saat reject). Approver tidak boleh sama dengan requester.
- FR-024: PR `REJECTED` dapat direvisi: dikembalikan ke `DRAFT` oleh requester (revisi tercatat).
- FR-025: Procurement Officer menandai PR `APPROVED` menjadi `IN_SOURCING` saat RFQ dibuat.

### 3.4 Sourcing (F-06, F-07, F-08)
- FR-030: Procurement Officer membuat RFQ (`RFQ-YYYYMM-NNNN`) dari PR `APPROVED`, memilih >= 1 vendor, menentukan batas waktu penawaran.
- FR-031: RFQ yang dikirim berstatus `SENT` (pencatatan, bukan pengiriman email).
- FR-032: Officer menginput Quotation per vendor: harga satuan per item, lead time, syarat bayar (teks), masa berlaku, lampiran file.
- FR-033: Sistem menampilkan tabel perbandingan: baris = item, kolom = vendor, total per vendor, penanda harga terendah.
- FR-034: Officer memilih satu Quotation sebagai `SELECTED` disertai justifikasi (wajib jika bukan harga terendah).
- FR-035: Pemilihan vendor memerlukan approval Procurement Manager (Approval tipe `QUOTATION`).

### 3.5 Purchase Order (F-09, F-10, F-14)
- FR-040: Setelah vendor di-approve, Officer menerbitkan PO (`PO-YYYYMM-NNNN`) otomatis berisi item dan harga dari quotation terpilih.
- FR-041: PO berstatus `PENDING_APPROVAL` sampai disetujui Procurement Manager, lalu `APPROVED`.
- FR-042: PO `APPROVED` dapat ditandai `SENT` (dicatat dikirim ke vendor) dan dicetak.
- FR-043: PO `REJECTED` kembali ke Officer untuk revisi atau pembatalan.

### 3.6 Goods Receipt (F-11)
- FR-050: Warehouse Receiver membuat GR terhadap PO berstatus `SENT` atau `PARTIALLY_RECEIVED`: nomor surat jalan, tanggal, qty diterima per item, kondisi (OK/RUSAK), catatan.
- FR-051: qty diterima per item tidak boleh melebihi sisa (qty PO - total diterima sebelumnya).
- FR-052: Jika semua item PO terpenuhi, PO dan PR menjadi `COMPLETED`; jika sebagian, `PARTIALLY_RECEIVED`.
- FR-053: Sistem **tidak** mengelola stok atau lokasi gudang.

### 3.7 Audit dan Dashboard (F-12, F-13, F-15)
- FR-060: Setiap perubahan status dokumen menulis AuditLog (objek, status lama, status baru, user, waktu, catatan).
- FR-061: Dashboard menampilkan jumlah dokumen per status dan antrean tugas sesuai role.
- FR-062: Daftar dokumen mendukung filter status, pencarian nomor, dan pagination.

### 3.8 AI Extractor (F-16, opsional)
- FR-070: Officer dapat upload gambar/PDF penawaran; sistem memanggil model vision dan mengembalikan JSON (item, qty, harga, lead time).
- FR-071: Hasil ekstraksi **hanya mengisi form sebagai draf**; user wajib meninjau dan menyimpan manual.
- FR-072: Jika API gagal, timeout, atau key tidak ada, tampil pesan dan form manual tetap tersedia.

## 4. State Machine (aturan transisi)

**PurchaseRequest**
```
DRAFT -> SUBMITTED -> APPROVED -> IN_SOURCING -> PO_ISSUED -> PARTIALLY_RECEIVED -> COMPLETED
              \-> REJECTED -> DRAFT (revisi)
Dari DRAFT/SUBMITTED/APPROVED/IN_SOURCING -> CANCELLED
```
**RFQ**: `DRAFT -> SENT -> CLOSED -> AWARDED`; `CANCELLED` dari DRAFT/SENT.
**Quotation**: `SUBMITTED -> SELECTED` (dipilih, menunggu approval Manager) `-> APPROVED | REJECTED`; `REJECTED -> SUBMITTED` (Officer memilih ulang).
**PurchaseOrder**: `PENDING_APPROVAL -> APPROVED -> SENT -> PARTIALLY_RECEIVED -> COMPLETED`; `PENDING_APPROVAL -> REJECTED -> PENDING_APPROVAL` (revisi); `CANCELLED` dari PENDING_APPROVAL/REJECTED/APPROVED.

Transisi di luar tabel di atas harus ditolak oleh service layer dengan error domain.

## 5. Non-Functional Requirements
| ID | Kategori | Requirement |
|---|---|---|
| NFR-01 | Keamanan | Password di-hash (Django default), CSRF aktif, ORM tanpa raw SQL berformat string |
| NFR-02 | Keamanan | Secret/API key hanya dari environment variable |
| NFR-03 | Auditability | Tidak ada hard delete pada PR, RFQ, Quotation, PO, GR |
| NFR-04 | Integritas data | Operasi multi-tabel dibungkus `transaction.atomic` |
| NFR-05 | Portabilitas | Berjalan dengan SQLite (default) dan PostgreSQL (Docker Compose) |
| NFR-06 | Maintainability | Logika bisnis di `services/`, view tipis, type hint pada service |
| NFR-07 | Testability | Test otomatis untuk state machine dan aturan bisnis kritis |
| NFR-08 | Usability | UI responsif dasar, pesan error jelas, bahasa Indonesia |
| NFR-09 | Reproducibility | `seed_data` + README: clone -> run dalam < 5 langkah |

## 6. Aturan Bisnis
- BR-01 Segregation of duties: pembuat PR tidak boleh approve PR yang sama.
- BR-02 Quotation hanya dapat dipilih dari RFQ milik PR terkait.
- BR-03 Total PO = jumlah (qty x harga satuan) dari quotation terpilih.
- BR-04 Harga dan qty PO tidak dapat diubah setelah `APPROVED`.
- BR-05 GR tidak boleh melebihi sisa qty PO.
- BR-06 Dokumen berstatus final (`COMPLETED`, `CANCELLED`, `REJECTED`) tidak dapat diubah kecuali transisi revisi yang diizinkan.

## 7. Matriks Role x Aksi
| Aksi | Admin | Req | DeptHead | Officer | Manager | WH |
|---|---|---|---|---|---|---|
| Kelola master data | Y | - | - | - | - | - |
| Buat/submit PR | - | Y | - | - | - | - |
| Approve PR | - | - | Y | - | - | - |
| Buat RFQ/Quotation | - | - | - | Y | - | - |
| Approve vendor/PO | - | - | - | - | Y | - |
| Terbit/kirim PO | - | - | - | Y | - | - |
| Buat GR | - | - | - | - | - | Y |
| Lihat dashboard | Y | Y | Y | Y | Y | Y |

## 8. Traceability
Setiap FR dipetakan ke ID fitur WBS (kolom `WBS_ID`) dan ke elemen BPMN (task name). Perubahan FR wajib memperbarui WBS dan BPMN.
