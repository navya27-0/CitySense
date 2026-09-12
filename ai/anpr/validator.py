"""License Plate Normalization and Validation Engine for BusSense-AI.

Provides positional character confusion matrix corrections, formatting normalization,
and regex-based validation rules for Indian vehicle registration formats.
"""

import re
import string
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, List

# Standard Indian License Plate Regex Formats:
# 1. Standard (e.g., TS09EA1234, AP28AB5678, DL3CAA1111, MH12DE1432, KA01MG2020)
#    - State Code (2 letters) + District/RTO Code (1-2 digits) + Series Code (1-3 letters) + Unique Number (4 digits)
STANDARD_INDIAN_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$")

# 2. Bharat Stage (BH Series, e.g., 22BH1234AA)
#    - Year of registration (2 digits) + 'BH' + Unique Number (4 digits) + Series (1-2 letters)
BHARAT_STAGE_PLATE_REGEX = re.compile(r"^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$")

# 3. Two-Wheeler / Commercial Alternate Formats (e.g., TS09A1234, DL1A1234)
SHORT_SERIES_PLATE_REGEX = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1}[0-9]{4}$")

# Recognized Indian State & Union Territory 2-Letter Codes
VALID_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN",
    "GA", "GJ", "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD",
    "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "PB", "PY", "RJ",
    "SK", "TN", "TR", "TS", "UK", "UP", "WB",
}

# OCR Positional Character Confusion Mappings
# When a letter is expected:
DIGIT_TO_LETTER = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "3": "E",
    "4": "A",
    "5": "S",
    "6": "G",
    "8": "B",
}

# When a digit is expected:
LETTER_TO_DIGIT = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "E": "3",
    "A": "4",
    "S": "5",
    "G": "6",
    "b": "6",
    "B": "8",
    "T": "7",
}


@dataclass
class ValidationResult:
    """Result of license plate normalization and validation."""
    raw_text: str
    normalized_text: str
    is_valid_format: bool
    plate_type: str  # 'STANDARD_INDIAN', 'BH_SERIES', 'UNVALIDATED_FORMAT'
    state_code: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "is_valid_format": self.is_valid_format,
            "plate_type": self.plate_type,
            "state_code": self.state_code,
            "rejection_reason": self.rejection_reason,
        }


class PlateValidator:
    """Validates and normalizes license plate strings using Indian registration rules."""

    @staticmethod
    def clean_text(raw_text: str) -> str:
        """Removes spaces, punctuation, hyphens, and non-alphanumeric characters, with HSRP 'IND' tag handling."""
        if not raw_text:
            return ""
        # Keep only ASCII alphanumeric characters and uppercase
        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()

        # Handle Indian High Security Registration Plate (HSRP) 'IND' badge prefix
        # e.g. 'INDTS09EA1234' -> 'TS09EA1234'
        if cleaned.startswith("IND") and len(cleaned) >= 9:
            # Check if the characters following IND form a plausible state prefix
            possible_state = cleaned[3:5]
            if possible_state in VALID_STATE_CODES or possible_state.isalpha():
                cleaned = cleaned[3:]

        return cleaned

    @classmethod
    def apply_positional_corrections(cls, cleaned: str) -> str:
        """Applies context-aware confusion matrix corrections based on plate structure.

        Standard structure (e.g. 10 chars: TS09EA1234):
        - Index 0..1: State Code -> Must be letters
        - Index 2..3: District Code -> Must be digits (if length 10)
        - Index 4..5: Series Code -> Must be letters
        - Index 6..9: Unique Sequence -> Must be digits
        """
        if len(cleaned) == 10:
            chars = list(cleaned)
            # Index 0, 1: State Code (Letters)
            chars[0] = DIGIT_TO_LETTER.get(chars[0], chars[0])
            chars[1] = DIGIT_TO_LETTER.get(chars[1], chars[1])

            # Index 2, 3: District Code (Digits)
            chars[2] = LETTER_TO_DIGIT.get(chars[2], chars[2])
            chars[3] = LETTER_TO_DIGIT.get(chars[3], chars[3])

            # Index 4, 5: Series Code (Letters)
            chars[4] = DIGIT_TO_LETTER.get(chars[4], chars[4])
            chars[5] = DIGIT_TO_LETTER.get(chars[5], chars[5])

            # Index 6, 7, 8, 9: Number (Digits)
            for i in range(6, 10):
                chars[i] = LETTER_TO_DIGIT.get(chars[i], chars[i])

            return "".join(chars)

        elif len(cleaned) == 9:
            # E.g. TS9EA1234 or TS09A1234
            chars = list(cleaned)
            # State code (0, 1)
            chars[0] = DIGIT_TO_LETTER.get(chars[0], chars[0])
            chars[1] = DIGIT_TO_LETTER.get(chars[1], chars[1])
            # Last 4 digits (5, 6, 7, 8)
            for i in range(5, 9):
                chars[i] = LETTER_TO_DIGIT.get(chars[i], chars[i])
            return "".join(chars)

        elif len(cleaned) == 11:
            # E.g. DL03CAA1111
            chars = list(cleaned)
            chars[0] = DIGIT_TO_LETTER.get(chars[0], chars[0])
            chars[1] = DIGIT_TO_LETTER.get(chars[1], chars[1])
            chars[2] = LETTER_TO_DIGIT.get(chars[2], chars[2])
            chars[3] = LETTER_TO_DIGIT.get(chars[3], chars[3])
            chars[4] = DIGIT_TO_LETTER.get(chars[4], chars[4])
            chars[5] = DIGIT_TO_LETTER.get(chars[5], chars[5])
            chars[6] = DIGIT_TO_LETTER.get(chars[6], chars[6])
            for i in range(7, 11):
                chars[i] = LETTER_TO_DIGIT.get(chars[i], chars[i])
            return "".join(chars)

        return cleaned

    @classmethod
    def validate_and_normalize(cls, raw_ocr_text: str) -> ValidationResult:
        """Normalizes and validates raw OCR text against Indian license plate rules.

        Args:
            raw_ocr_text: Raw uncleaned string returned by OCR.

        Returns:
            ValidationResult with normalized text, validity flag, and rejection reason if invalid.
        """
        if not raw_ocr_text or not raw_ocr_text.strip():
            return ValidationResult(
                raw_text=raw_ocr_text or "",
                normalized_text="",
                is_valid_format=False,
                plate_type="UNVALIDATED_FORMAT",
                state_code=None,
                rejection_reason="Empty or whitespace-only OCR text",
            )

        cleaned = cls.clean_text(raw_ocr_text)

        if len(cleaned) < 6:
            return ValidationResult(
                raw_text=raw_ocr_text,
                normalized_text=cleaned,
                is_valid_format=False,
                plate_type="UNVALIDATED_FORMAT",
                state_code=None,
                rejection_reason=f"Character length ({len(cleaned)}) is too short for a valid license plate (minimum 6 characters required)",
            )

        if len(cleaned) > 12:
            return ValidationResult(
                raw_text=raw_ocr_text,
                normalized_text=cleaned,
                is_valid_format=False,
                plate_type="UNVALIDATED_FORMAT",
                state_code=None,
                rejection_reason=f"Character length ({len(cleaned)}) exceeds maximum expected license plate length (12 characters)",
            )

        # 1. Check Bharat Stage (BH) Series FIRST
        if BHARAT_STAGE_PLATE_REGEX.match(cleaned) or (len(cleaned) in (9, 10) and (cleaned[2:4] == "BH" or ("BH" in cleaned and cleaned[:2].isdigit()))):
            chars = list(cleaned)
            # Index 0, 1: Year (Digits)
            chars[0] = LETTER_TO_DIGIT.get(chars[0], chars[0])
            chars[1] = LETTER_TO_DIGIT.get(chars[1], chars[1])
            # Index 2, 3: 'BH' (Letters)
            chars[2] = "B"
            chars[3] = "H"
            # Index 4..7: Number (Digits)
            for i in range(4, min(8, len(chars))):
                chars[i] = LETTER_TO_DIGIT.get(chars[i], chars[i])
            # Index 8..: Series (Letters)
            for i in range(8, len(chars)):
                chars[i] = DIGIT_TO_LETTER.get(chars[i], chars[i])
            bh_corr = "".join(chars)
            if BHARAT_STAGE_PLATE_REGEX.match(bh_corr):
                return ValidationResult(
                    raw_text=raw_ocr_text,
                    normalized_text=bh_corr,
                    is_valid_format=True,
                    plate_type="BH_SERIES",
                    state_code="BH",
                    rejection_reason=None,
                )

        # 2. Check Standard Indian Formats with Positional Corrections
        corrected = cls.apply_positional_corrections(cleaned)

        if STANDARD_INDIAN_PLATE_REGEX.match(corrected) or SHORT_SERIES_PLATE_REGEX.match(corrected):
            state = corrected[:2]
            if state in VALID_STATE_CODES:
                return ValidationResult(
                    raw_text=raw_ocr_text,
                    normalized_text=corrected,
                    is_valid_format=True,
                    plate_type="STANDARD_INDIAN",
                    state_code=state,
                    rejection_reason=None,
                )
            else:
                return ValidationResult(
                    raw_text=raw_ocr_text,
                    normalized_text=corrected,
                    is_valid_format=False,
                    plate_type="UNVALIDATED_FORMAT",
                    state_code=state,
                    rejection_reason=f"Invalid state prefix '{state}'. Recognized Indian state codes include: TS, AP, DL, MH, KA, etc.",
                )

        # 3. Check if prefix is invalid state code
        state_prefix = corrected[:2] if len(corrected) >= 2 and corrected[:2].isalpha() else (cleaned[:2] if cleaned[:2].isalpha() else None)
        if state_prefix and state_prefix not in VALID_STATE_CODES:
            return ValidationResult(
                raw_text=raw_ocr_text,
                normalized_text=corrected,
                is_valid_format=False,
                plate_type="UNVALIDATED_FORMAT",
                state_code=state_prefix,
                rejection_reason=f"Invalid state prefix '{state_prefix}'. Recognized Indian state codes include: TS, AP, DL, MH, KA, etc.",
            )

        # If regex pattern does not match even after correction:
        return ValidationResult(
            raw_text=raw_ocr_text,
            normalized_text=corrected,
            is_valid_format=False,
            plate_type="UNVALIDATED_FORMAT",
            state_code=state_prefix,
            rejection_reason=f"String '{corrected}' does not match standard Indian registration pattern (e.g. SS DD AA NNNN)",
        )
