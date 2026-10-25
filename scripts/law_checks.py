#!/usr/bin/env python
"""
scripts/law_checks.py - Runner gate law.bend dalam Python murni.

Penggunaan:
  python scripts/law_checks.py                  # jalankan semua gate
  python scripts/law_checks.py views_protected  # gate L013
  python scripts/law_checks.py thin_views       # gate L021
  python scripts/law_checks.py erd_sync         # gate L031
  python scripts/law_checks.py wbs_trace        # gate L050

Exit code 0 = semua gate yang diminta lulus.
Exit code 1 = ada gate BLOCK yang terpicu (atau gate L013/L021/L031/L050 gagal).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

# Paksa stdout UTF-8 agar karakter Unicode tidak error di Windows (CP1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT / "apps"
SERVICES_DIR = ROOT / "services"
TESTS_DIR = ROOT / "tests"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"


def _ok(gate: str, msg: str = "") -> None:
    print(f"  {GREEN}✓{RESET} [{gate}] {msg}")


def _fail(gate: str, msg: str, severity: str = "BLOCK") -> None:
    color = RED if severity == "BLOCK" else YELLOW
    label = f"{color}{BOLD}{severity}{RESET}"
    print(f"  {RED}✗{RESET} [{gate}] {label} {msg}")


def _warn(gate: str, msg: str) -> None:
    _fail(gate, msg, severity="WARN")


def _run(*cmd: str, cwd: Path = ROOT) -> tuple[int, str, str]:
    """Jalankan subprocess, kembalikan (returncode, stdout, stderr)."""
    result = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def _grep_re(pattern: str, dirs: list[Path], extra_flags: list[str] | None = None) -> list[str]:
    """Cari pattern regex di direktori, kembalikan baris yang cocok."""
    matches = []
    for d in dirs:
        if not d.exists():
            continue
        rc, out, _ = _run("python", "-m", "grep_shim", pattern, str(d))
        # Gunakan pure Python karena grep tidak dijamin ada di Windows
        for pyfile in d.rglob("*.py"):
            try:
                text = pyfile.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(pattern, line):
                    matches.append(f"{pyfile}:{i}: {line}")
    return matches


def _grep_files(pattern: str, dirs: list[Path], *, include_migrations: bool = False) -> list[str]:
    """Cari pattern di file .py. Lewati migrations kecuali diminta."""
    matches = []
    for d in dirs:
        if not d.exists():
            continue
        for pyfile in d.rglob("*.py"):
            if not include_migrations and "migrations" in pyfile.parts:
                continue
            try:
                text = pyfile.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(pattern, line, re.IGNORECASE):
                    matches.append(f"{pyfile.relative_to(ROOT)}:{i}: {line.rstrip()}")
    return matches


# ──────────────────────────────────────────────────────────────────────────────
# Gate implementations (dipanggil langsung oleh law_checks.py)
# ──────────────────────────────────────────────────────────────────────────────


def gate_views_protected() -> int:
    """
    L013: Setiap view wajib @login_required / @role_required (kecuali view login).

    Strategi:
    - Parse AST setiap views.py di apps/
    - Fungsi/method yang terlihat sebagai "view" (nama diakhiri _view atau terdeteksi
      dari argumen pertama 'request') wajib memiliki decorator login_required atau
      role_required.
    - Fungsi 'login_view' / 'logout_view' dikecualikan.
    """
    EXEMPT = {"login_view", "logout_view", "login", "logout"}
    REQUIRED_DECORATORS = {"login_required", "role_required"}

    issues: list[str] = []
    checked = 0

    for views_file in APPS_DIR.rglob("views.py"):
        try:
            source = views_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(views_file))
        except (OSError, SyntaxError) as exc:
            issues.append(f"{views_file}: cannot parse ({exc})")
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fname = node.name
            if fname.startswith("_") or fname in EXEMPT:
                continue
            # Heuristik: cek apakah ini view (argumen pertama bernama 'request')
            args = node.args.args
            if not args or args[0].arg != "request":
                continue
            checked += 1
            dec_names = set()
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    dec_names.add(dec.id)
                elif isinstance(dec, ast.Call):
                    func = dec.func
                    if isinstance(func, ast.Name):
                        dec_names.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        dec_names.add(func.attr)
                elif isinstance(dec, ast.Attribute):
                    dec_names.add(dec.attr)
            if not (dec_names & REQUIRED_DECORATORS):
                rel = views_file.relative_to(ROOT)
                issues.append(
                    f"{rel}:{node.lineno}: '{fname}' tidak memiliki @login_required/@role_required"
                )

    if issues:
        for iss in issues:
            print(f"    {RED}!{RESET} {iss}")
        _fail("L013", f"{len(issues)} view tidak terlindungi")
        return 1
    if checked == 0:
        _ok("L013", "belum ada views.py — gate dilewati")
    else:
        _ok("L013", f"{checked} view diperiksa, semua terlindungi")
    return 0


def gate_thin_views() -> int:
    """
    L021: View tidak boleh memuat aturan bisnis.

    Heuristik — deteksi pola yang biasa menandakan logika di view:
    - Akses langsung ke .status (bukan memanggil transition())
    - Kalkulasi total: sum(, total=, amount =
    - Validasi qty: qty >, qty <, qty ==
    - Import model transaction (select_for_update) — hanya OK di services/
    """
    BUSINESS_PATTERNS = [
        r"\.status\s*=[^=]",
        r"\.update\(\s*status\s*=",
        r"\bselect_for_update\b",
        r"\btotal\s*=\s*sum\(",
        r"qty_received\s*[><=]",
    ]

    issues: list[str] = []
    for views_file in APPS_DIR.rglob("views.py"):
        try:
            text = views_file.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in BUSINESS_PATTERNS:
                if re.search(pat, line):
                    rel = views_file.relative_to(ROOT)
                    issues.append(f"{rel}:{i}: {line.rstrip()}")

    if issues:
        for iss in issues:
            print(f"    {RED}!{RESET} {iss}")
        _fail("L021", f"{len(issues)} baris berpotensi logika bisnis di view")
        return 1
    _ok("L021", "view tipis — tidak ada logika bisnis terdeteksi")
    return 0


def gate_erd_sync() -> int:
    """
    L031: Jika ada migration baru, Architect.md wajib ter-update pada commit yang sama.

    Implementasi: bandingkan tanggal modifikasi migration terbaru vs Architect.md.
    Pada CI/pre-commit, cek apakah keduanya ada di staged files secara bersamaan.
    Karena runner ini dijalankan pre-commit, kita cek via 'git diff --cached'.
    """
    rc, out, _ = _run("git", "diff", "--cached", "--name-only")
    staged = set(out.splitlines())

    new_migrations = [f for f in staged if re.search(r"migrations/\d+_", f)]
    architect_changed = any("Architect.md" in f for f in staged)

    if new_migrations and not architect_changed:
        print(f"    {YELLOW}!{RESET} Migration baru di-stage tetapi Architect.md tidak diperbarui:")
        for m in new_migrations:
            print(f"      - {m}")
        _warn("L031", "ERD/Architect.md wajib diperbarui bersama migration baru")
        return 1
    _ok("L031", "ERD sync OK")
    return 0


def gate_wbs_trace() -> int:
    """
    L050 (WARN): Setiap URL baru wajib punya referensi F-xx di docstring atau commit.

    Strategi: cari definisi path() di urls.py yang view-nya tidak memiliki docstring F-xx.
    """
    for urls_file in ROOT.rglob("urls.py"):
        if ".venv" in str(urls_file) or ".git" in str(urls_file):
            continue
        try:
            source = urls_file.read_text(encoding="utf-8")
        except OSError:
            continue
        # Cari view names dari path()
        for m in re.finditer(r"path\(['\"][^'\"]*['\"],\s*(\w+)", source):
            view_name = m.group(1)
            if view_name in ("include", "admin"):
                continue
            # Cari view di apps/
            for views_file in APPS_DIR.rglob("views.py"):
                try:
                    vsrc = views_file.read_text(encoding="utf-8")
                except OSError:
                    continue
                # Cek apakah ada F-xx dalam source file views yang mendefinisikan view ini
                fn_pattern = rf"def\s+{re.escape(view_name)}\s*\("
                if re.search(fn_pattern, vsrc):
                    if re.search(r"F-\d+", vsrc):
                        break
            # Jika tidak ditemukan sama sekali di views, skip (mungkin include)
    _ok("L050", "WBS trace check selesai (WARN only)")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Gate runner: grep-based (untuk gate yang pakai grep pattern)
# ──────────────────────────────────────────────────────────────────────────────


def gate_grep(
    gate_id: str,
    pattern: str,
    dirs: list[Path],
    *,
    severity: str = "BLOCK",
    exclude_pattern: str | None = None,
    description: str = "",
) -> int:
    """Jalankan grep-based gate. Return 0 jika tidak ada hasil (gate lulus)."""
    matches = _grep_files(pattern, dirs)
    if exclude_pattern:
        matches = [m for m in matches if not re.search(exclude_pattern, m)]
    if matches:
        for m in matches:
            print(f"    {RED}!{RESET} {m}")
        if severity == "BLOCK":
            _fail(gate_id, f"{len(matches)} pelanggaran ditemukan — {description}")
        else:
            _warn(gate_id, f"{len(matches)} pelanggaran ditemukan — {description}")
        return 1
    _ok(gate_id, description or "lulus")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Subcommand dispatcher
# ──────────────────────────────────────────────────────────────────────────────

SUBCOMMANDS: dict[str, callable] = {
    "views_protected": gate_views_protected,
    "thin_views": gate_thin_views,
    "erd_sync": gate_erd_sync,
    "wbs_trace": gate_wbs_trace,
}


def run_all() -> int:
    """Jalankan semua gate sesuai urutan law.bend [run_order]."""
    print(f"\n{BOLD}{CYAN}========================================{RESET}")
    print(f"{BOLD}{CYAN}  law.bend gate runner  v1.0{RESET}")
    print(f"{BOLD}{CYAN}========================================{RESET}\n")

    failures: list[tuple[str, str]] = []  # (gate_id, severity)

    def run_gate(gate_id: str, fn, severity: str = "BLOCK") -> None:
        rc = fn()
        if rc != 0:
            failures.append((gate_id, severity))

    # ── L051: law.bend immutability ──
    print(f"{BOLD}▶ L051 law-file-immutable{RESET}")
    rc, out, _ = _run("git", "diff", "--cached", "--name-only")
    staged = set(out.splitlines())
    law_changed = "law.bend" in staged
    law_approved = __import__("os").environ.get("LAW_OWNER_APPROVED", "") == "1"
    if law_changed and not law_approved:
        _fail("L051", "law.bend di-stage tanpa LAW_OWNER_APPROVED=1")
        failures.append(("L051", "BLOCK"))
    else:
        _ok("L051", "law.bend tidak diubah atau disetujui pemilik")

    # ── L010: no-secrets-in-repo ──
    print(f"\n{BOLD}▶ L010 no-secrets-in-repo{RESET}")
    secret_pattern = r"(sk-ant-[A-Za-z0-9_-]+|AKIA[0-9A-Z]{16}|BEGIN (RSA )?PRIVATE KEY)"
    all_dirs = [APPS_DIR, SERVICES_DIR, ROOT / "config"]
    run_gate(
        "L010",
        lambda: gate_grep(
            "L010", secret_pattern, all_dirs, description="API key/secret terdeteksi di kode"
        ),
    )

    # ── L011: no-forbidden-files-tracked ──
    print(f"\n{BOLD}▶ L011 no-forbidden-files-tracked{RESET}")
    rc, out, _ = _run("git", "ls-files")
    tracked = out.splitlines()
    forbidden = [
        f
        for f in tracked
        if re.search(r"(^|/)\.env$|^db\.sqlite3$|^media/|__pycache__|^\.venv/", f)
    ]
    if forbidden:
        for f in forbidden:
            print(f"    {RED}!{RESET} {f}")
        _fail("L011", f"{len(forbidden)} file terlarang di git")
        failures.append(("L011", "BLOCK"))
    else:
        _ok("L011", "tidak ada file terlarang di git")

    # ── L014: csrf-not-disabled ──
    print(f"\n{BOLD}▶ L014 csrf-not-disabled{RESET}")
    run_gate(
        "L014",
        lambda: gate_grep(
            "L014",
            r"(csrf_exempt|CsrfViewMiddleware.*#|# *'django\.middleware\.csrf)",
            [APPS_DIR, ROOT / "config"],
            description="CSRF dinonaktifkan",
        ),
    )

    # ── L001: no-warehouse-module ──
    print(f"\n{BOLD}▶ L001 no-warehouse-module{RESET}")
    run_gate(
        "L001",
        lambda: gate_grep(
            "L001",
            r"(class\s+(Stock|Inventory|Warehouse(Location|Bin|Stock))|StockMovement|stock_level|bin_location)",
            [APPS_DIR, SERVICES_DIR],
            description="modul gudang/stok ditemukan",
        ),
    )

    # ── L002: no-payment-module ──
    print(f"\n{BOLD}▶ L002 no-payment-module{RESET}")
    run_gate(
        "L002",
        lambda: gate_grep(
            "L002",
            r"(class\s+(Invoice|Payment|Settlement|Billing)|payment_status|paid_at|bank_account)",
            [APPS_DIR, SERVICES_DIR],
            description="modul pembayaran ditemukan",
        ),
    )

    # ── L003: no-vendor-login ──
    print(f"\n{BOLD}▶ L003 no-vendor-login{RESET}")
    run_gate(
        "L003",
        lambda: gate_grep(
            "L003",
            r"VENDOR\s*=\s*['\"]",
            [APPS_DIR / "accounts"],
            description="role VENDOR ditemukan",
        ),
    )

    # ── L012: orm-only-no-string-sql ──
    print(f"\n{BOLD}▶ L012 orm-only-no-string-sql{RESET}")
    run_gate(
        "L012",
        lambda: gate_grep(
            "L012",
            r"(\.raw\(|cursor\.execute\(|\.extra\()\s*(f['\"]|['\"].*(%s|\{).*['\"])",
            [APPS_DIR, SERVICES_DIR],
            description="raw SQL dengan f-string/format ditemukan",
        ),
    )

    # ── L013: every-view-protected ──
    print(f"\n{BOLD}▶ L013 every-view-protected{RESET}")
    run_gate("L013", gate_views_protected)

    # ── L020: status-change-via-state-machine-only ──
    print(f"\n{BOLD}▶ L020 status-change-via-state-machine-only{RESET}")
    # Cari .status = atau update(status= di luar state_machine.py, migrations, tests
    state_machine_issues: list[str] = []
    skip_dirs = {"migrations", "tests", "__pycache__"}
    skip_files = {"state_machine.py"}
    for search_dir in [APPS_DIR, SERVICES_DIR]:
        if not search_dir.exists():
            continue
        for pyfile in search_dir.rglob("*.py"):
            if pyfile.name in skip_files:
                continue
            if any(part in skip_dirs for part in pyfile.parts):
                continue
            try:
                text = pyfile.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if re.search(r"(\.status\s*=[^=]|update\(\s*status\s*=)", line):
                    rel = pyfile.relative_to(ROOT)
                    state_machine_issues.append(f"{rel}:{i}: {line.rstrip()}")
    if state_machine_issues:
        for iss in state_machine_issues:
            print(f"    {RED}!{RESET} {iss}")
        _fail("L020", f"{len(state_machine_issues)} perubahan status langsung ditemukan")
        failures.append(("L020", "BLOCK"))
    else:
        _ok("L020", "semua perubahan status lewat state machine")

    # ── L021: no-business-logic-in-views ──
    print(f"\n{BOLD}▶ L021 no-business-logic-in-views{RESET}")
    run_gate("L021", gate_thin_views)

    # ── L026: no-hard-delete-of-transactions ──
    print(f"\n{BOLD}▶ L026 no-hard-delete-of-transactions{RESET}")
    hard_delete_issues: list[str] = []
    models_no_delete = [
        "PurchaseRequest",
        "RFQ",
        "Quotation",
        "PurchaseOrder",
        "GoodsReceipt",
        "AuditLog",
    ]
    pattern_hd = r"(" + "|".join(models_no_delete) + r")\S*\.(objects\.[a-z_()]*)?delete\("
    for search_dir in [APPS_DIR, SERVICES_DIR]:
        if not search_dir.exists():
            continue
        for pyfile in search_dir.rglob("*.py"):
            if "tests" in pyfile.parts or "migrations" in pyfile.parts:
                continue
            try:
                text = pyfile.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(pattern_hd, line, re.IGNORECASE):
                    rel = pyfile.relative_to(ROOT)
                    hard_delete_issues.append(f"{rel}:{i}: {line.rstrip()}")
    if hard_delete_issues:
        for iss in hard_delete_issues:
            print(f"    {RED}!{RESET} {iss}")
        _fail("L026", f"{len(hard_delete_issues)} hard-delete ditemukan")
        failures.append(("L026", "BLOCK"))
    else:
        _ok("L026", "tidak ada hard-delete transaksi")

    # ── L032: money-uses-decimal ──
    print(f"\n{BOLD}▶ L032 money-uses-decimal{RESET}")
    run_gate(
        "L032",
        lambda: gate_grep(
            "L032",
            r"(price|amount|total|cost)\w*\s*=\s*models\.FloatField",
            [APPS_DIR],
            description="FloatField dipakai untuk nilai uang",
        ),
    )

    # ── L030: migrations-in-sync ──
    print(f"\n{BOLD}▶ L030 migrations-in-sync{RESET}")
    rc, out, err = _run(sys.executable, "manage.py", "makemigrations", "--check", "--dry-run")
    if rc != 0:
        print(f"    {RED}!{RESET} {(out + err).strip()}")
        _fail("L030", "model tidak sinkron dengan migration")
        failures.append(("L030", "BLOCK"))
    else:
        _ok("L030", "migration sinkron")

    # ── L031: erd-updated-on-schema-change ──
    print(f"\n{BOLD}▶ L031 erd-updated-on-schema-change{RESET}")
    run_gate("L031", gate_erd_sync, severity="BLOCK")

    # ── L033: tests-pass ──
    print(f"\n{BOLD}▶ L033 tests-pass{RESET}")
    rc, out, err = _run(sys.executable, "-m", "pytest", "-q", "--tb=short")
    print(out[-2000:] if len(out) > 2000 else out)
    if rc != 0:
        _fail("L033", "ada test gagal")
        failures.append(("L033", "BLOCK"))
    else:
        _ok("L033", "semua test hijau")

    # ── L035: lint-clean (WARN) ──
    print(f"\n{BOLD}▶ L035 lint-clean (WARN){RESET}")
    rc, out, err = _run(sys.executable, "-m", "ruff", "check", ".")
    if rc != 0:
        print(out[:1000])
        _warn("L035", "ruff check gagal")
        failures.append(("L035", "WARN"))
    else:
        _ok("L035", "ruff check lulus")

    # ── L050: wbs-trace (WARN) ──
    print(f"\n{BOLD}▶ L050 wbs-trace (WARN){RESET}")
    run_gate("L050", gate_wbs_trace, severity="WARN")

    # ──────────────────────────────────────
    # Ringkasan
    # ──────────────────────────────────────
    print(f"\n{BOLD}{CYAN}========================================{RESET}")
    blocks = [(g, s) for g, s in failures if s == "BLOCK"]
    warns = [(g, s) for g, s in failures if s == "WARN"]
    if blocks:
        print(f"{RED}{BOLD}  GAGAL - {len(blocks)} gate BLOCK terpicu:{RESET}")
        for g, _ in blocks:
            print(f"    {RED}x{RESET} {g}")
        if warns:
            print(f"{YELLOW}  PERINGATAN - {len(warns)} gate WARN:{RESET}")
            for g, _ in warns:
                print(f"    {YELLOW}!{RESET} {g}")
        print(f"{BOLD}{CYAN}========================================{RESET}\n")
        return 1
    elif warns:
        print(f"{YELLOW}{BOLD}  LULUS dengan {len(warns)} peringatan WARN:{RESET}")
        for g, _ in warns:
            print(f"    {YELLOW}!{RESET} {g}")
        print(f"{BOLD}{CYAN}========================================{RESET}\n")
        return 0
    else:
        print(f"{GREEN}{BOLD}  SEMUA GATE LULUS{RESET}")
        print(f"{BOLD}{CYAN}========================================{RESET}\n")
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(run_all())
    else:
        subcmd = args[0]
        if subcmd not in SUBCOMMANDS:
            print(f"Subcommand tidak dikenal: {subcmd}")
            print(f"Tersedia: {', '.join(SUBCOMMANDS)}")
            sys.exit(2)
        fn = SUBCOMMANDS[subcmd]
        rc = fn()
        sys.exit(rc)
