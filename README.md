# Procurement App

Aplikasi pengadaan (PR -> approval -> RFQ -> quotation -> PO -> Goods Receipt). Django 5 + SQLite/PostgreSQL.

> Status: alur lengkap (PR -> approval -> RFQ -> quotation -> PO -> GR) beserta UI Bootstrap/HTMX.
> Ekstraksi penawaran via AI opsional (F-16) dan hanya prefill form, tidak menyimpan otomatis.

## Menjalankan
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python scripts/seed_data.py
python manage.py runserver
pytest
```
Database default SQLite. Untuk PostgreSQL/Supabase isi `DATABASE_URL` di `.env` (lihat `Architect.md` bagian 9).
Akun demo: `admin/admin123`, serta `requester|depthead|officer|manager|warehouse` dengan password `demo123`.

## Dokumen
`PRD.md` | `SRS.md` | `Architect.md` | `Design.md` | `CLAUDE.md` / `AGENTS.md` | `law.bend`

- BPMN swimlane: `docs/BPMN.pdf` (sumber: `docs/BPMN.md`)
- WBS: `docs/WBS.xlsx` (sumber: `docs/WBS.md`, ekspor: `docs/WBS.csv`)
