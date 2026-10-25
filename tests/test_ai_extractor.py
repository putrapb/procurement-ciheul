"""
Tests: AI extractor (gate L040, L041 — opsional).

Gate L040: output AI tidak auto-save ke DB.
Gate L041: kegagalan API tidak memblokir input manual.

Karena AI extractor bersifat opsional (F-16), modul ini mungkin belum ada.
Test menangani kasus tersebut secara graceful.
"""

import pytest

pytestmark = pytest.mark.django_db


def _import_extractor():
    """Import ai_extractor jika ada. Return None jika belum diimplementasikan."""
    try:
        from services import ai_extractor

        return ai_extractor
    except ImportError:
        return None


def test_extraction_does_not_persist():
    """
    Gate L040: Output AI hanya prefill form; tidak menyimpan ke DB tanpa konfirmasi user.

    Jika ai_extractor belum ada, test ini lulus (opsional).
    """
    extractor = _import_extractor()
    if extractor is None:
        pytest.skip("ai_extractor belum diimplementasikan (opsional F-16)")

    # Pastikan fungsi extract_quotation mengembalikan dict/dataclass, bukan menyimpan ke DB
    from apps.sourcing.models import Quotation

    count_before = Quotation.objects.count()
    try:
        extractor.extract_quotation(file=None)
    except Exception:
        # Kegagalan API diizinkan — yang penting tidak persist
        pass

    count_after = Quotation.objects.count()
    assert count_after == count_before, "AI extractor tidak boleh menyimpan Quotation ke DB"


def test_failure_falls_back_to_manual():
    """
    Gate L041: Kegagalan/timeout/ketiadaan API key tidak memblokir input manual.

    Jika ai_extractor belum ada, test ini lulus (opsional).
    """
    extractor = _import_extractor()
    if extractor is None:
        pytest.skip("ai_extractor belum diimplementasikan (opsional F-16)")

    # Pastikan kegagalan API menghasilkan empty result + pesan, bukan exception tak tertangkap
    import os

    original_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        result = extractor.extract_quotation(file=None)
        # Hasil harus berupa dict/dataclass dengan field yang dapat dipakai form
        assert result is not None, "Harus mengembalikan hasil kosong, bukan None"
    except Exception as exc:
        pytest.fail(f"ai_extractor.extract_quotation raise exception tanpa fallback: {exc}")
    finally:
        if original_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = original_key
