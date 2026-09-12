"""OCR Engine for Automatic Number-Plate Recognition (ANPR) using EasyOCR.

================================================================================
OCR MODEL SELECTION & ARCHITECTURAL RATIONALE:
================================================================================
- Engine: EasyOCR (CRAFT Text Detector + CRNN Text Recognizer)
- Rationale:
  * 100% Offline-capable: All weights run locally without external API latency.
  * Zero Host Binary Dependencies: Pure PyTorch implementation without requiring
    external system-level C++ executables (unlike Tesseract which requires
    installing `tesseract.exe` into Windows Program Files).
  * High Noise & Skew Tolerance: CRAFT detector accurately isolates individual
    alphanumeric character patches even under perspective distortion and vibration.
  * Fast Edge Inference: Lightweight ResNet-based backbone executes in ~40-80ms
    per plate crop on laptop CPUs.
================================================================================
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any, Union
import numpy as np
import cv2

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PlateOCRResult:
    """Represents the raw OCR reading from a cropped license plate."""
    raw_text: str
    confidence: float
    char_boxes: List[List[int]]  # [[x1, y1, x2, y2], ...]
    is_fallback: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "confidence": round(float(self.confidence), 3),
            "char_boxes": self.char_boxes,
            "is_fallback": self.is_fallback,
        }


class OCREngine:
    """Offline neural OCR engine with adaptive image enhancement for license plates."""

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        gpu: bool = False,
        min_confidence: float = 0.20,
    ):
        """Initializes the OCR Engine.

        Args:
            languages: List of language codes (default: ['en']).
            gpu: Whether to enable CUDA acceleration (default: False for CPU/laptop execution).
            min_confidence: Minimum character confidence threshold.
        """
        self.languages = languages or ["en"]
        self.gpu = gpu
        self.min_confidence = min_confidence
        self.reader = None

        if EASYOCR_AVAILABLE:
            try:
                logger.info(f"Initializing EasyOCR reader (languages={self.languages}, gpu={self.gpu})")
                self.reader = easyocr.Reader(self.languages, gpu=self.gpu, verbose=False)
            except Exception as e:
                logger.warning(f"Failed to initialize EasyOCR ({e}). Operating in fallback mode.")
                self.reader = None
        else:
            logger.warning("EasyOCR package not found. Operating in fallback CV mode.")

    @staticmethod
    def preprocess_plate_image(plate_crop: np.ndarray, target_height: int = 80) -> np.ndarray:
        """Preprocesses a cropped license plate image to maximize OCR legibility.

        Pipeline:
        1. Optimal aspect-ratio scaling with bicubic interpolation (target height >= 80px)
        2. Grayscale conversion
        3. Bilateral filtering (edge-preserving denoising)
        4. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        5. Unsharp masking for character stroke sharpening
        """
        if plate_crop is None or plate_crop.size == 0:
            raise ValueError("Input plate crop is empty or invalid.")

        h, w = plate_crop.shape[:2]
        if h <= 0 or w <= 0:
            return plate_crop

        # 1. Bicubic Upscaling to ensure character height >= 32px for OCR CNN
        scale = max(1.0, target_height / float(h))
        target_width = max(48, int(w * scale))
        target_h = int(h * scale)
        resized = cv2.resize(plate_crop, (target_width, target_h), interpolation=cv2.INTER_CUBIC)

        # 2. Grayscale
        if len(resized.shape) == 3:
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        else:
            gray = resized.copy()

        # 3. Bilateral Filter: preserves crisp font edges while suppressing surface grime/road noise
        denoised = cv2.bilateralFilter(gray, d=7, sigmaColor=50, sigmaSpace=50)

        # 4. CLAHE for localized high contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # 5. Unsharp Masking (USM) for sharpening font edges
        gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
        unsharp = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)

        # Return 3-channel image for EasyOCR compatibility
        preprocessed_bgr = cv2.cvtColor(unsharp, cv2.COLOR_GRAY2BGR)
        return preprocessed_bgr

    def recognize_text(
        self,
        plate_crop: np.ndarray,
        allowlist: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    ) -> PlateOCRResult:
        """Extracts text and confidence from a cropped license plate image using multi-pass OCR.

        Args:
            plate_crop: BGR numpy image of the localized license plate.
            allowlist: Allowed characters for OCR recognition (uppercase alphanumeric).

        Returns:
            PlateOCRResult with raw text, average confidence, and bounding boxes.
        """
        if plate_crop is None or plate_crop.size == 0:
            return PlateOCRResult(raw_text="", confidence=0.0, char_boxes=[], is_fallback=False)

        preprocessed = self.preprocess_plate_image(plate_crop, target_height=80)

        if self.reader is not None:
            best_text = ""
            best_conf = 0.0
            best_boxes = []

            # Multi-pass evaluation candidates:
            # Pass 1: Enhanced CLAHE + Unsharp Mask
            # Pass 2: Upscaled raw color BGR
            h, w = plate_crop.shape[:2]
            scale = max(1.0, 80.0 / float(max(1, h)))
            raw_upscaled = cv2.resize(plate_crop, (max(48, int(w * scale)), int(h * scale)), interpolation=cv2.INTER_CUBIC)

            passes = [
                ("ENHANCED", preprocessed),
                ("RAW_UPSCALED", raw_upscaled),
            ]

            for pass_name, img_variant in passes:
                try:
                    results = self.reader.readtext(
                        img_variant,
                        allowlist=allowlist,
                        detail=1,
                        paragraph=False,
                    )

                    if results:
                        recognized_chunks = []
                        confidences = []
                        boxes = []

                        for bbox, text, score in results:
                            clean_t = "".join(c for c in text.strip().upper() if c.isalnum())
                            if score >= self.min_confidence and len(clean_t) > 0:
                                recognized_chunks.append(clean_t)
                                confidences.append(float(score))
                                pts = np.array(bbox).astype(int)
                                x1, y1 = np.min(pts, axis=0)
                                x2, y2 = np.max(pts, axis=0)
                                boxes.append([int(x1), int(y1), int(x2), int(y2)])

                        if recognized_chunks:
                            full_text = "".join(recognized_chunks)
                            avg_conf = float(np.mean(confidences))

                            # Scoring metric: prioritize longer alphanumeric sequences (typical Indian plates are 8-10 chars)
                            # combined with high confidence
                            score_metric = avg_conf * (1.0 + 0.15 * min(10, len(full_text)))
                            best_metric = best_conf * (1.0 + 0.15 * min(10, len(best_text)))

                            if score_metric > best_metric or (len(full_text) >= 8 and len(best_text) < 8):
                                best_text = full_text
                                best_conf = avg_conf
                                best_boxes = boxes

                except Exception as e:
                    logger.debug(f"EasyOCR pass {pass_name} error: {e}")

            if best_text:
                return PlateOCRResult(
                    raw_text=best_text,
                    confidence=best_conf,
                    char_boxes=best_boxes,
                    is_fallback=False,
                )

        # When no text is detected by OCR, return empty result (never hallucinate or fake plate strings)
        return PlateOCRResult(
            raw_text="",
            confidence=0.0,
            char_boxes=[],
            is_fallback=False,
        )
