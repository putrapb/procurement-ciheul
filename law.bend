# =============================================================================
# law.bend - GATE TERAKHIR SEBELUM EKSEKUSI / COMMIT
# =============================================================================
# Aturan di file ini TIDAK BOLEH dibengkokkan (bend) oleh agent maupun developer.
# Jika salah satu gate terpicu:
#   1. Eksekusi dihentikan (tidak ada commit/push/merge)
#   2. Perubahan di-ROLLBACK ke commit hijau terakhir
#   3. Pelanggaran dicatat di LAW_VIOLATIONS.log
#   4. Kode HARUS direvisi agar sesuai aturan (bukan aturan yang diubah)
#   5. Gate dijalankan ulang sampai lulus
#
# Dilarang: melemahkan pattern, menghapus gate, menambah pengecualian,
#           menandai gate sebagai "skip", atau mengedit file ini
#           tanpa instruksi eksplisit pemilik repo.
#
# Severity:
#   BLOCK = rollback otomatis, wajib revisi
#   WARN  = dicatat, tidak boleh ada saat submit akhir (dianggap BLOCK di release)
# =============================================================================

[meta]
project        = procurement-app
version        = 1.0
owner_approval = required_to_modify_this_file
violation_log  = LAW_VIOLATIONS.log
on_violation   = rollback_and_revise
rollback_to    = last_green_commit

# -----------------------------------------------------------------------------
# A. SCOPE
# -----------------------------------------------------------------------------

[gate L001]
name      = no-warehouse-module
severity  = BLOCK
rule      = Dilarang membuat fitur gudang (stok, inventory, mutasi, lokasi rak).
            GR hanya mencatat penerimaan, bukan mengelola stok.
check     = grep -riE "(class\s+(Stock|Inventory|Warehouse(Location|Bin|Stock))|StockMovement|stock_level|bin_location)" apps/ services/
violates_if = ada hasil
fix_hint  = Hapus model/service stok. Berhenti di GoodsReceipt/GRItem.

[gate L002]
name      = no-payment-module
severity  = BLOCK
rule      = Dilarang membuat fitur pembayaran (invoice, payment, settlement).
check     = grep -riE "(class\s+(Invoice|Payment|Settlement|Billing)|payment_status|paid_at|bank_account)" apps/ services/
violates_if = ada hasil
fix_hint  = Hapus. Pembayaran di luar scope.

[gate L003]
name      = no-vendor-login
severity  = BLOCK
rule      = Vendor bukan user login. Role vendor tidak boleh ada di enum Role.
check     = grep -riE "VENDOR\s*=\s*['\"]" apps/accounts/
violates_if = ada hasil
fix_hint  = Data vendor hanya di masterdata.Vendor, penawaran diinput Procurement Officer.

# -----------------------------------------------------------------------------
# B. KEAMANAN
# -----------------------------------------------------------------------------

[gate L010]
name      = no-secrets-in-repo
severity  = BLOCK
rule      = API key, password, SECRET_KEY produksi tidak boleh ada di source.
check     = grep -rEn "(sk-ant-[A-Za-z0-9_-]+|ANTHROPIC_API_KEY\s*=\s*['\"][^'\"]+|AKIA[0-9A-Z]{16}|service_role|postgres(ql)?://[^:@/ ]+:[^@ ]{3,}@[a-z0-9.-]+\.supabase\.(co|com)|BEGIN (RSA )?PRIVATE KEY)" . --exclude-dir=.git --exclude-dir=.venv --exclude=.env.example
violates_if = ada hasil
fix_hint  = Pindahkan ke environment variable, isi placeholder di .env.example.

[gate L011]
name      = no-forbidden-files-tracked
severity  = BLOCK
rule      = File berikut tidak boleh masuk git: .env, db.sqlite3, media/, __pycache__/, .venv/
check     = git ls-files | grep -E "(^|/)(\.env|db\.sqlite3)$|^media/|__pycache__|^\.venv/"
violates_if = ada hasil
fix_hint  = git rm --cached, tambahkan ke .gitignore.

[gate L012]
name      = orm-only-no-string-sql
severity  = BLOCK
rule      = Dilarang raw SQL dengan f-string/format/concat (risiko SQL injection).
check     = grep -rEn "(\.raw\(|cursor\.execute\(|\.extra\()\s*(f['\"]|['\"].*(%s|\{).*['\"]\s*(%|\.format|\+))" apps/ services/
violates_if = ada hasil
fix_hint  = Gunakan ORM atau query terparameter.

[gate L013]
name      = every-view-protected
severity  = BLOCK
rule      = Setiap view wajib memakai @login_required / @role_required (kecuali login).
check     = python scripts/law_checks.py views_protected
violates_if = exit code != 0
fix_hint  = Tambahkan decorator role pada view yang disebut.

[gate L014]
name      = csrf-not-disabled
severity  = BLOCK
rule      = Dilarang @csrf_exempt dan menghapus CsrfViewMiddleware.
check     = grep -rEn "(csrf_exempt|CsrfViewMiddleware.*#|# *'django.middleware.csrf)" apps/ config/
violates_if = ada hasil
fix_hint  = Hapus csrf_exempt; gunakan {% csrf_token %}.

# -----------------------------------------------------------------------------
# C. ARSITEKTUR DAN INTEGRITAS BISNIS
# -----------------------------------------------------------------------------

[gate L020]
name      = status-change-via-state-machine-only
severity  = BLOCK
rule      = Assign langsung ".status =" atau .update(status=...) hanya boleh di
            services/state_machine.py. Tempat lain wajib memanggil transition().
check     = grep -rEn "(\.status\s*=[^=]|update\(\s*status\s*=)" apps/ services/ --exclude=state_machine.py --exclude-dir=migrations --exclude-dir=tests
violates_if = ada hasil
fix_hint  = Panggil services.state_machine.transition(obj, to_status, user, note).

[gate L021]
name      = no-business-logic-in-views
severity  = BLOCK
rule      = View tidak boleh memuat aturan bisnis (hitung total, validasi transisi,
            cek sisa qty). View hanya parsing, panggil service, render.
check     = python scripts/law_checks.py thin_views
violates_if = exit code != 0
fix_hint  = Pindahkan logika ke services/.

[gate L022]
name      = every-transition-writes-audit
severity  = BLOCK
rule      = Setiap perubahan status wajib menulis AuditLog dalam transaksi yang sama.
check     = pytest tests/test_audit.py -q
violates_if = test gagal
fix_hint  = Pastikan transition() memanggil audit_service.log() di dalam atomic.

[gate L023]
name      = segregation-of-duties
severity  = BLOCK
rule      = Pembuat PR tidak boleh meng-approve PR miliknya sendiri (BR-01).
check     = pytest tests/test_approval_rules.py::test_requester_cannot_self_approve -q
violates_if = test gagal
fix_hint  = Tolak di approval_service jika approver == requester.

[gate L024]
name      = receipt-never-exceeds-po
severity  = BLOCK
rule      = qty GR tidak boleh melebihi sisa qty PO (BR-05).
check     = pytest tests/test_receiving.py::test_over_receipt_rejected -q
violates_if = test gagal
fix_hint  = Validasi sisa qty di receiving_service, atomic + select_for_update.

[gate L025]
name      = po-immutable-after-approval
severity  = BLOCK
rule      = Harga dan qty PO tidak boleh berubah setelah APPROVED (BR-04).
check     = pytest tests/test_orders.py::test_po_immutable_after_approved -q
violates_if = test gagal
fix_hint  = Tolak update item/harga bila status bukan PENDING_APPROVAL/DRAFT.

[gate L026]
name      = no-hard-delete-of-transactions
severity  = BLOCK
rule      = PR, RFQ, Quotation, PO, GR, AuditLog tidak boleh dihapus (hard delete).
            Gunakan status CANCELLED. Hanya PR berstatus DRAFT yang boleh dihapus.
check     = grep -rEn "(PurchaseRequest|RFQ|Quotation|PurchaseOrder|GoodsReceipt|AuditLog)\S*\.(objects\.[a-z_()]*)?delete\(" apps/ services/ --exclude-dir=tests
violates_if = ada hasil di luar penghapusan PR DRAFT di requisition_service
fix_hint  = Ganti dengan transisi ke CANCELLED.

[gate L027]
name      = audit-log-append-only
severity  = BLOCK
rule      = AuditLog tidak boleh di-update atau di-delete.
check     = pytest tests/test_audit.py::test_audit_log_append_only -q
violates_if = test gagal
fix_hint  = Override save()/delete() AuditLog agar menolak perubahan.

# -----------------------------------------------------------------------------
# D. SCHEMA DAN KUALITAS
# -----------------------------------------------------------------------------

[gate L030]
name      = migrations-in-sync
severity  = BLOCK
rule      = Model tidak boleh berbeda dari migration.
check     = python manage.py makemigrations --check --dry-run
violates_if = exit code != 0
fix_hint  = Buat migration, jangan edit migration lama yang sudah di-commit.

[gate L031]
name      = erd-updated-on-schema-change
severity  = BLOCK
rule      = Jika ada file migrations baru, Architect.md (bagian ERD) wajib ikut berubah
            pada commit yang sama.
check     = python scripts/law_checks.py erd_sync
violates_if = exit code != 0
fix_hint  = Perbarui ERD dan tabel schema di Architect.md.

[gate L032]
name      = money-uses-decimal
severity  = BLOCK
rule      = Nilai uang wajib DecimalField, dilarang FloatField.
check     = grep -rEn "(price|amount|total|cost)\w*\s*=\s*models\.FloatField" apps/
violates_if = ada hasil
fix_hint  = Ganti ke DecimalField(max_digits=15, decimal_places=2).

[gate L033]
name      = tests-pass
severity  = BLOCK
rule      = Seluruh test harus hijau.
check     = pytest -q
violates_if = exit code != 0
fix_hint  = Perbaiki penyebab (debug), jangan hapus/skip test.

[gate L034]
name      = no-test-tampering
severity  = BLOCK
rule      = Dilarang menambah @pytest.mark.skip/xfail atau menghapus assert
            untuk meloloskan gate.
check     = git diff --cached -U0 -- tests/ | grep -E "^\+.*(pytest\.mark\.(skip|xfail)|@unittest\.skip)|^-.*\bassert\b"
violates_if = ada hasil
fix_hint  = Perbaiki kode produksi, bukan test.

[gate L035]
name      = lint-clean
severity  = WARN
rule      = Kode lolos ruff check dan format.
check     = ruff check . && ruff format --check .
violates_if = exit code != 0
fix_hint  = ruff check --fix && ruff format .

# -----------------------------------------------------------------------------
# E. AI (OPSIONAL)
# -----------------------------------------------------------------------------

[gate L040]
name      = ai-never-autosaves
severity  = BLOCK
rule      = Output AI hanya prefill form. Dilarang menyimpan hasil ekstraksi AI
            langsung ke tabel Quotation tanpa konfirmasi user.
check     = pytest tests/test_ai_extractor.py::test_extraction_does_not_persist -q
violates_if = test gagal
fix_hint  = Return dataclass/dict ke view; persist hanya dari form submit.

[gate L041]
name      = ai-has-manual-fallback
severity  = BLOCK
rule      = Kegagalan/timeout/ketiadaan API key tidak boleh memblokir input manual.
check     = pytest tests/test_ai_extractor.py::test_failure_falls_back_to_manual -q
violates_if = test gagal
fix_hint  = Tangkap exception di extractor, kembalikan hasil kosong + pesan.

# -----------------------------------------------------------------------------
# F. KONSISTENSI DOKUMEN
# -----------------------------------------------------------------------------

[gate L050]
name      = feature-traceable-to-wbs
severity  = WARN
rule      = Setiap fitur/URL baru harus punya referensi ID WBS (F-xx) di commit
            message atau docstring.
check     = python scripts/law_checks.py wbs_trace
violates_if = exit code != 0
fix_hint  = Tambahkan "F-xx" ke commit/docstring, atau update WBS.

[gate L051]
name      = law-file-immutable
severity  = BLOCK
rule      = law.bend tidak boleh berubah kecuali ada tanda persetujuan pemilik
            (env LAW_OWNER_APPROVED=1 pada commit tersebut).
check     = git diff --cached --name-only | grep -qx "law.bend" && [ "$LAW_OWNER_APPROVED" != "1" ]
violates_if = exit code == 0
fix_hint  = Batalkan perubahan law.bend dan revisi kode agar patuh.

# =============================================================================
# URUTAN EKSEKUSI GATE (fail-fast pada BLOCK)
# =============================================================================
[run_order]
1 = L051
2 = L010, L011, L014
3 = L001, L002, L003
4 = L012, L013, L020, L021, L026, L032
5 = L030, L031
6 = L033, L034, L022, L023, L024, L025, L027, L040, L041
7 = L035, L050

[on_violation_procedure]
step1 = stop_execution
step2 = git restore --staged --worktree .   # atau git revert ke last_green_commit
step3 = append_to LAW_VIOLATIONS.log: <timestamp> <gate_id> <file> <reason>
step4 = revise_code_to_comply               # bukan mengubah law.bend
step5 = rerun_all_gates
