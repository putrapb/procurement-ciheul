"""
AI extractor — prefill quotation dari dokumen penawaran (F-16, opsional).

Aturan:
  - Tidak pernah menyimpan data ke DB; hasil hanya dipakai untuk prefill form.
  - Kegagalan API / ketiadaan key / format file salah TIDAK memblokir input manual
    (gate L041): selalu mengembalikan ExtractionResult dengan pesan error.
  - Tanpa dependency tambahan (hanya stdlib + Django settings).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.conf import settings

DEFAULT_MODEL = "claude-3-5-sonnet-latest"
MAX_FILE_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT = 30

_PROMPT = """Ekstrak data penawaran vendor dari dokumen ini.
Balas HANYA JSON valid (tanpa markdown) dengan bentuk:
{
  "items": [{"item_name": "nama barang", "qty": 1, "unit_price": 1000}],
  "lead_time_days": 7,
  "valid_until": "YYYY-MM-DD",
  "terms": "syarat pembayaran"
}
Gunakan null jika data tidak tersedia. Jangan mengarang angka."""


@dataclass
class ExtractedItem:
    item_name: str
    qty: Decimal | None = None
    unit_price: Decimal | None = None


@dataclass
class ExtractionResult:
    items: list[ExtractedItem] = field(default_factory=list)
    lead_time_days: int | None = None
    valid_until: date | None = None
    terms: str = ""
    message: str = ""
    error: str = ""


def _api_key() -> str:
    return (
        getattr(settings, "ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ).strip()


def _model() -> str:
    return (
        getattr(settings, "AI_EXTRACT_MODEL", "")
        or os.environ.get("AI_EXTRACT_MODEL", "")
        or DEFAULT_MODEL
    )


def _to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None


def _to_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_payload(text: str) -> ExtractionResult:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except (TypeError, ValueError):
        return ExtractionResult(
            message="AI tidak mengembalikan JSON yang valid; isi form secara manual.",
            error="invalid_json",
        )

    items = []
    for raw in data.get("items") or []:
        name = str(raw.get("item_name") or "").strip()
        if not name:
            continue
        items.append(
            ExtractedItem(
                item_name=name,
                qty=_to_decimal(raw.get("qty")),
                unit_price=_to_decimal(raw.get("unit_price")),
            )
        )

    lead_time = data.get("lead_time_days")
    try:
        lead_time_value = int(lead_time) if lead_time is not None else None
    except (TypeError, ValueError):
        lead_time_value = None

    return ExtractionResult(
        items=items,
        lead_time_days=lead_time_value,
        valid_until=_to_date(data.get("valid_until")),
        terms=str(data.get("terms") or ""),
        message=(
            f"AI mengekstrak {len(items)} item. Periksa dan lengkapi sebelum menyimpan."
            if items
            else "AI tidak menemukan item; isi form secara manual."
        ),
    )


def extract_quotation(file) -> ExtractionResult:
    """
    Ekstrak penawaran dari file PDF/gambar. Selalu mengembalikan ExtractionResult.

    `file` adalah UploadedFile (atau objek ber-.read()/.name/.content_type).
    """
    if file is None:
        return ExtractionResult(
            message="Pilih file penawaran terlebih dahulu.",
            error="missing_file",
        )

    api_key = _api_key()
    if not api_key:
        return ExtractionResult(
            message=(
                "Ekstraksi AI belum dikonfigurasi. Isi harga secara manual "
                "(set ANTHROPIC_API_KEY untuk mengaktifkan F-16)."
            ),
            error="missing_api_key",
        )

    media_type = (
        getattr(file, "content_type", "")
        or mimetypes.guess_type(getattr(file, "name", ""))[0]
        or ""
    )
    if media_type == "application/pdf":
        block_type = "document"
    elif media_type.startswith("image/"):
        block_type = "image"
    else:
        return ExtractionResult(
            message="Format file harus PDF atau gambar (JPG/PNG).",
            error="unsupported_media_type",
        )

    try:
        payload_bytes = file.read()
    except Exception as exc:
        return ExtractionResult(
            message="File tidak dapat dibaca; isi form secara manual.",
            error=str(exc),
        )

    if not payload_bytes:
        return ExtractionResult(message="File kosong.", error="empty_file")
    if len(payload_bytes) > MAX_FILE_BYTES:
        return ExtractionResult(message="Ukuran file melebihi 10 MB.", error="file_too_large")

    body = {
        "model": _model(),
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": block_type,
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(payload_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return ExtractionResult(
            message="AI tidak dapat dihubungi; isi form secara manual.",
            error=str(exc),
        )

    text = "".join(
        part.get("text", "")
        for part in data.get("content", [])
        if isinstance(part, dict) and part.get("type") == "text"
    )
    if not text:
        return ExtractionResult(
            message="AI tidak mengembalikan hasil; isi form secara manual.",
            error="empty_response",
        )
    return _parse_payload(text)
