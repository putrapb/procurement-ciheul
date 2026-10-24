# AGENTS.md

Aturan lengkap ada di `CLAUDE.md` (baca dulu). Ringkas:

1. Baca `PRD.md`, `SRS.md`, `Architect.md`, `Design.md` sebelum mengubah kode.
2. **Sebelum menganggap tugas selesai, baca `law.bend` dan jalankan semua gate.**
   Jika ada gate terpicu: rollback perubahan, catat di `LAW_VIOLATIONS.log`, revisi kode agar patuh.
   Dilarang mengubah, melemahkan, atau melewati `law.bend`.
3. Scope: tanpa modul gudang/stok dan pembayaran.
4. Logika bisnis hanya di `services/`; status berubah hanya lewat `services.state_machine.transition()`.
5. Database default SQLite; PostgreSQL/Supabase hanya lewat `DATABASE_URL` (hanya sebagai database,
   tanpa Supabase Auth/RLS/SDK). Schema hanya dari migration Django.
6. Jangan commit `.env`, `db.sqlite3`, API key.
7. Command: `pytest`, `ruff check .`, `python manage.py makemigrations --check --dry-run`.
