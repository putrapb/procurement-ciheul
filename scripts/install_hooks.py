#!/usr/bin/env python
"""Install pre-commit hook dari scripts/pre-commit ke .git/hooks/pre-commit."""

import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "scripts" / "pre-commit"
dst = ROOT / ".git" / "hooks" / "pre-commit"

shutil.copy2(src, dst)
# Tambahkan bit executable (tidak berpengaruh di Windows tapi tidak menyebabkan error)
current = dst.stat().st_mode
dst.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print(f"✓ Pre-commit hook terinstall di {dst}")
print("  Setiap 'git commit' sekarang akan menjalankan law_checks.py otomatis.")
