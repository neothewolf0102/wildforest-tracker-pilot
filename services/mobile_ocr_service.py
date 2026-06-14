from __future__ import annotations

import re
from typing import Any

MOBILE_OCR_LAYOUT_PROFILES: dict[str, dict[str, Any]] = {
    "profile_wild_shards_wf_gold": {
        "display_name": "Wild Shards / WF / Gold",
        "slots": ["wild_shards", "wf", "gold"],
    }
}

NUMBER_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:[ ,]\d{3})+|\d+)(?:\.\d+)?(?![A-Za-z0-9])"
)


def _clean_ocr_noise(text: str) -> str:
    return str(text or "").replace("|", "1").replace("O", "0").replace("o", "0")


def _normalize_number(value: str) -> float:
    normalized = str(value or "").replace(" ", "").replace(",", "")
    return float(normalized)


def extract_mobile_ocr_numbers(text: str) -> list[float]:
    cleaned = _clean_ocr_noise(text)
    return [_normalize_number(match.group(0)) for match in NUMBER_TOKEN_PATTERN.finditer(cleaned)]


def parse_mobile_ocr_paste(text: str, profile_key: str) -> dict[str, Any]:
    if profile_key not in MOBILE_OCR_LAYOUT_PROFILES:
        raise ValueError("Unknown Mobile OCR Paste layout profile.")

    profile = MOBILE_OCR_LAYOUT_PROFILES[profile_key]
    slots = list(profile["slots"])
    numbers = extract_mobile_ocr_numbers(text)
    warnings: list[str] = []

    if not str(text or "").strip():
        warnings.append("Pasted OCR text is empty.")
    if len(numbers) < len(slots):
        warnings.append(f"Found {len(numbers)} number(s); expected {len(slots)}. Fill missing values manually before saving.")
    if len(numbers) > len(slots):
        warnings.append(f"Found {len(numbers)} numbers; using the first {len(slots)} and ignoring the rest.")

    values: dict[str, int | float | None] = {slot: None for slot in slots}
    for slot, number in zip(slots, numbers):
        if slot in {"wild_shards", "gold"}:
            values[slot] = int(number)
        else:
            values[slot] = float(number)

    return {
        "profile_key": profile_key,
        "profile_display_name": profile["display_name"],
        "numbers_found": numbers,
        "values": values,
        "warnings": warnings,
    }
