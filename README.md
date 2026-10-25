# Procurement App

Aplikasi pengadaan end-to-end: **PR -> approval -> RFQ -> quotation -> vendor selection -> PO -> Goods Receipt**.
Django 5.2 + SQLite (default) / PostgreSQL, UI Bootstrap 5 + HTMX.

> Status: alur lengkap beserta UI, audit trail, dan dashboard.
> Ekstraksi penawaran via AI opsional (F-16); hasil AI hanya mengisi form, tidak menyimpan otomatis.

## 1. Kebutuhan

- Python **3.12+** (diuji dengan Python 3.13)
- Git
- SQLite (bawaan Python) atau PostgreSQL 16 (opsional)
- Docker (opsional, untuk menjalankan PostgreSQL + aplikasi)

## 2. Instalasi Lokal (Windows / PowerShell)

```powershell
# 1. Clone repository
git clone https://github.com/[username]/[repository].git
cd procurement-ciheul

# 2. Buat dan aktifkan virtual environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Jika PowerShell menolak aktivasi script:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 3. Install dependensi
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4. Siapkan environment
Copy-Item .env.example .env
# Edit .env minimal: SECRET_KEY, ALLOWED_HOSTS

# 5. Migrasi database + data demo
python manage.py migrate
python scripts/seed_data.py

# 6. Jalankan aplikasi
python manage.py runserver
```

Buka: **http://127.0.0.1:8000/**

## 3. Instalasi Lokal (Linux / macOS)

```bash
git clone https://github.com/[username]/[repository].git
cd procurement-ciheul

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp .env.example .env
# Edit .env minimal: SECRET_KEY, ALLOWED_HOSTS

python manage.py migrate
python scripts/seed_data.py
python manage.py runserver
```

## 4. Konfigurasi `.env`

```dotenv
DEBUG=1
SECRET_KEY=ganti-dengan-secret-acak
ALLOWED_HOSTS=localhost,127.0.0.1

# Kosongkan untuk SQLite (default).
# DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/dbname
# DB_DISABLE_SERVER_SIDE_CURSORS=1

# Opsional untuk AI extractor.
ANTHROPIC_API_KEY=
```

- **SQLite (default):** tidak perlu mengisi `DATABASE_URL`.
- **PostgreSQL/Supabase:** isi `DATABASE_URL` dengan connection string database. Supabase hanya
  dipakai sebagai database; aplikasi tidak memakai Supabase Auth/RLS/SDK.
- **AI extractor:** tanpa `ANTHROPIC_API_KEY`, input quotation manual tetap berfungsi.
- Jangan commit `.env`, `db.sqlite3`, `media/`, atau API key.

## 5. Menjalankan dengan Docker (PostgreSQL)

```bash
docker compose up --build -d
docker compose exec web python scripts/seed_data.py
```

Aplikasi: **http://127.0.0.1:8000/**. Hentikan dengan `docker compose down`.
Database PostgreSQL tetap tersimpan di volume `pgdata`.

## 6. Akun Demo

Dibuat oleh `python scripts/seed_data.py`:

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Admin |
| `requester` | `demo123` | Requester |
| `depthead` | `demo123` | Dept Head |
| `officer` | `demo123` | Procurement Officer |
| `manager` | `demo123` | Procurement Manager |
| `warehouse` | `demo123` | Warehouse Receiver |

Vendor bukan akun login. Data vendor merupakan master data yang dikelola Admin; quotation
diinput oleh Procurement Officer.

## 7. Alur Penggunaan

1. **Requester** membuat PR multi-item, lalu submit.
2. **Dept Head** approve/reject PR. Jika reject, Requester merevisi lalu submit ulang.
3. **Officer** membuat RFQ dari PR yang approved, memilih vendor, lalu mengirim RFQ.
4. **Officer** menginput quotation tiap vendor (manual atau upload + AI extract).
5. **Officer** membandingkan penawaran dan memilih vendor.
6. **Manager** menyetujui pilihan vendor.
7. **Officer** menerbitkan PO.
8. **Manager** menyetujui PO.
9. **Officer** menandai PO terkirim dan dapat mencetak PO.
10. **Warehouse** mencatat Goods Receipt. Partial receipt didukung sampai seluruh qty terpenuhi.

## 8. Halaman Utama

| Halaman | URL |
|---|---|
| Login | `/accounts/login/` |
| Dashboard | `/` |
| Purchase Request | `/pr/` |
| Approval PR | `/approvals/` |
| RFQ / Sourcing | `/sourcing/rfq/` |
| Purchase Order | `/orders/po/` |
| Goods Receipt | `/receiving/` |
| Django Admin | `/admin/` |

## 9. Test dan Quality Gate

Aktifkan virtual environment terlebih dahulu.

```bash
pytest -q
python manage.py makemigrations --check --dry-run
python manage.py check
ruff check .
ruff format --check .
python scripts/law_checks.py
```

Jika `ruff` tidak dikenali di PowerShell, gunakan `.\.venv\Scripts\ruff.exe check .`.

## 10. Struktur Proyek

```text
apps/            # Django apps: accounts, masterdata, requisitions, sourcing, orders,
                 # receiving, approvals, audit, core
services/        # logika bisnis, state machine, audit, numbering, AI extractor
templates/       # UI Bootstrap/HTMX
tests/           # unit, integration, view/template, regression
scripts/         # seed data, law gate runner, install hooks
docs/            # BPMN dan WBS
config/          # settings dan URL utama
```

## 11. Dokumentasi

- `PRD.md` - kebutuhan produk dan fitur (F-xx)
- `SRS.md` - functional/non-functional requirements (FR-xxx)
- `Architect.md` - arsitektur, ERD, state machine
- `Design.md` - UI/UX
- `CLAUDE.md` / `AGENTS.md` - aturan pengembangan
- `law.bend` - gate kepatuhan yang tidak boleh diubah
- **BPMN swimlane:** `docs/BPMN.pdf` (sumber Mermaid: `docs/BPMN.md`)
- **WBS:** `docs/WBS.xlsx` (sumber: `docs/WBS.md`, ekspor: `docs/WBS.csv`)

## 12. Troubleshooting

- **`Activate.ps1 cannot be loaded`** → jalankan
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, lalu aktifkan ulang venv.
- **`No module named django`** → pastikan virtual environment aktif dan dependensi sudah di-install.
- **`Invalid HTTP_HOST header`** → tambahkan host yang dipakai ke `ALLOWED_HOSTS` di `.env`.
- **PostgreSQL menolak koneksi** → cek `DATABASE_URL`; untuk transaction pooler tambahkan
  `DB_DISABLE_SERVER_SIDE_CURSORS=1`.
- **AI extractor gagal** → pastikan `ANTHROPIC_API_KEY` valid; jika tidak, gunakan input manual.
