# CLAUDE.md - Instruksi untuk Claude Code

## Konteks Proyek
Aplikasi **Procurement** (take-home test Software Engineer, Ciheul Technologies). Alur: PR -> approval -> RFQ -> quotation -> pilih vendor -> PO -> Goods Receipt. Deadline: **25 Okt 2026 23:59:59**.

Dokumen acuan (baca sebelum mengubah kode):
- `PRD.md` : apa dan kenapa, scope
- `SRS.md` : requirement, state machine, aturan bisnis
- `Architect.md` : arsitektur, schema, struktur repo
- `Design.md` : UI/UX
- `law.bend` : **aturan yang tidak boleh dilanggar (gate terakhir)**

## Aturan Utama
1. **`law.bend` adalah otoritas tertinggi.** Sebelum menganggap tugas selesai, jalankan gate. Jika ada gate terpicu, perubahan di-rollback dan harus direvisi sesuai `law.bend`. Dilarang membengkokkan, melemahkan, menghapus, atau menonaktifkan aturan untuk meloloskan perubahan.
2. Jangan membuat fitur **gudang** (stok/inventory) atau **pembayaran** (invoice/payment).
3. Logika bisnis hanya di `services/`. View tipis.
4. Ubah status hanya lewat `services/state_machine.transition()`.
5. Jangan commit `.env`, `db.sqlite3`, API key, atau folder `media/`.
6. Perubahan schema -> buat migration dan perbarui ERD di `Architect.md`.
7. Fitur baru -> rujuk ID di WBS (F-xx) dan perbarui `SRS.md` bila requirement berubah.
8. Jika ragu antara cepat dan benar, pilih benar. Jika scope terlalu besar, potong AI/dashboard lebih dulu, bukan schema atau state machine.

## Tech Stack
Python 3.12, Django 5, SQLite (default) / PostgreSQL (Docker atau Supabase via `DATABASE_URL`, hanya sebagai DB), Bootstrap 5 + HTMX, pytest-django, ruff.

## Command
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python scripts/seed_data.py          # akun demo + data contoh
python manage.py runserver

pytest                                # test
ruff check . && ruff format --check . # lint
python manage.py makemigrations --check --dry-run
docker compose up --build             # PostgreSQL
```

## Konvensi Kode
- PEP 8, `ruff`, type hint pada fungsi service.
- Nama: model `PascalCase`, fungsi/variabel `snake_case`, konstanta `UPPER_CASE`.
- Status berupa `TextChoices` pada model, bukan string literal tersebar.
- Satu service function = satu use case, dibungkus `transaction.atomic`.
- Error domain lewat exception khusus (`InvalidTransition`, `BusinessRuleViolation`), view menangkap dan menampilkan pesan.
- Komentar hanya untuk "kenapa", bukan "apa".
- Commit message: `type(scope): ringkas`, mis. `feat(orders): add PO approval flow`.
- Satu commit = satu perubahan logis; jangan campur refactor dan fitur.

## Urutan Kerja (per fitur)
1. Baca FR terkait di `SRS.md` dan gate di `law.bend`.
2. Model + migration -> service + test -> view + template.
3. Jalankan `pytest`, `ruff`, dan gate `law.bend`.
4. Commit hanya jika semua hijau.

## Prosedur Saat Gate `law.bend` Terpicu
1. Hentikan eksekusi; jangan commit atau push.
2. Rollback perubahan yang melanggar (`git restore` / `git revert` ke commit hijau terakhir).
3. Catat pelanggaran di `LAW_VIOLATIONS.log` (ID gate, file, alasan).
4. Revisi pendekatan agar patuh pada aturan, bukan mengubah aturan.
5. Jalankan ulang gate sampai lulus.
Mengubah `law.bend` hanya boleh atas instruksi eksplisit pemilik repo.

## Akun Demo (seed)
| Role | Username | Password |
|---|---|---|
| Admin | admin | admin123 |
| Requester | requester | demo123 |
| Dept Head | depthead | demo123 |
| Procurement Officer | officer | demo123 |
| Procurement Manager | manager | demo123 |
| Warehouse Receiver | warehouse | demo123 |

(Hanya untuk demo lokal; wajib ada peringatan di README.)

## Definition of Done
- Lulus `pytest`, `ruff`, `makemigrations --check`, dan semua gate `law.bend`.
- Sesuai SRS dan konsisten dengan BPMN/WBS.
- README dan ERD ter-update bila relevan.
