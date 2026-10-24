# Procurement App

Aplikasi pengadaan (PR -> approval -> RFQ -> quotation -> PO -> Goods Receipt). Django 5 + SQLite/PostgreSQL.

> Status: fondasi (model, migration, state machine, audit, penomoran, test). UI/view menyusul.

## Menjalankan
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
pytest
```
Database default SQLite. Untuk PostgreSQL/Supabase isi `DATABASE_URL` di `.env` (lihat `Architect.md` bagian 9).

## Dokumen
`PRD.md` | `SRS.md` | `Architect.md` | `Design.md` | `CLAUDE.md` / `AGENTS.md` | `law.bend`
