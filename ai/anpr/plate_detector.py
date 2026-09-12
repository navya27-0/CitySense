"""Number Plate Localizer & Detection Module for BusSense-AI.

Supports two-tier plate localization:
1. Custom trained YOLO License Plate weights if present at `models/number_plates/best.pt` or `models/anpr/best.pt`.
2. Adaptive Morphological & Geometric Edge Candidate Extractor for robust zero-dependency
   plate localization on detected vehicle crops.
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any, Union
import numpy as np
import cv2

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PlateDetection:
    """Represents a localized license plate within a video frame."""
    plate_box: List[int]  # [x1, y1, x2, y2] in full frame coordinates
    vehicle_box: List[int]  # [vx1, vy1, vx2, vy2]
    confidence: float
    plate_crop: np.ndarray  # BGR cropped license plate image
    vehicle_crop: np.ndarray  # BGR cropped vehicle image
    aspect_ratio: float
    method: str  # 'YOLO_PLATE_MODEL' or 'ADAPTIVE_MORPHOLOGICAL'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plate_box": [int(v) for v in self.plate_box],
            "vehicle_box": [int(v) for v in self.vehicle_box],
            "confidence": round(float(self.confidence), 3),
            "aspect_ratio": round(float(self.aspect_ratio), 2),
            "method": self.method,
        }


class PlateDetector:
    """Localizes license plates within detected vehicles using custom YOLO or morphological filtering."""

    def __init__(
        self,
        custom_weights_path: Union[str, Path] = "models/number_plates/best.pt",
        conf_threshold: float = 0.35,
        device: str = "cpu",
    ):
        """Initializes the PlateDetector.

        Args:
            custom_weights_path: Path to custom YOLO plate detection weights.
            conf_threshold: Confidence threshold for plate localization.
            device: Compute device ('cpu', 'cuda', 'mps').
        """
        self.weights_path = Path(custom_weights_path)
        self.conf_threshold = conf_threshold
        self.device = device
        self.yolo_model = None

        self._load_detector()

    def _load_detector(self) -> None:
        """Loads custom YOLO weights if present on disk; otherwise logs fallback mode."""
        if not YOLO_AVAILABLE:
            logger.info("Ultralytics not available. Operating PlateDetector in morphological mode.")
            return

        # Check path variations
        candidates = [
            self.weights_path,
            Path("models/number_plates/best.pt"),
            Path("models/anpr/best.pt"),
            Path(__file__).resolve().parent.parent.parent / "models" / "number_plates" / "best.pt",
            Path(__file__).resolve().parent.parent.parent / "models" / "anpr" / "best.pt",
        ]

        found_weights = None
        for c in candidates:
            if c.exists() and c.is_file():
                found_weights = c
                break

        if found_weights:
            try:
                logger.info(f"Loading custom Plate Detection YOLO weights: {found_weights}")
                self.yolo_model = YOLO(str(found_weights))
            except Exception as e:
                logger.warning(f"Failed to load custom plate YOLO weights from {found_weights} ({e}). Falling back to morphological extractor.")
                self.yolo_model = None
        else:
            logger.info("Custom plate YOLO weights not found. Operating in adaptive morphological localization mode.")
            self.yolo_model = None

    def detect_plate_in_vehicle(
        self,
        frame: np.ndarray,
        vehicle_box: List[int],
        vehicle_type: str = "car",
    ) -> Optional[PlateDetection]:
        """Localizes license plate within a vehicle bounding box.

        Args:
            frame: Full BGR frame image.
            vehicle_box: [vx1, vy1, vx2, vy2] bounding box of the vehicle in the frame.
            vehicle_type: Type of vehicle ('car', 'bus', 'truck', 'motorcycle', 'bicycle').

        Returns:
            PlateDetection if a plate is localized, or None.
        """
        if frame is None or frame.size == 0 or not vehicle_box:
            return None

        fh, fw = frame.shape[:2]
        vx1, vy1, vx2, vy2 = [max(0, int(v)) for v in vehicle_box]
        vx2 = min(fw, vx2)
        vy2 = min(fh, vy2)

        vw = vx2 - vx1
        vh = vy2 - vy1

        if vw < 30 or vh < 30:
            return None

        vehicle_crop = frame[vy1:vy2, vx1:vx2]
        if vehicle_crop.size == 0:
            return None

        # 1. Tier 1: Custom YOLO Plate Detector (if model weights loaded)
        if self.yolo_model is not None:
            try:
                results = self.yolo_model.predict(
                    source=vehicle_crop,
                    conf=self.conf_threshold,
                    device=self.device,
                    verbose=False,
                )
                if results and len(results) > 0 and len(results[0].boxes) > 0:
                    best_box = results[0].boxes[0]
                    px1, py1, px2, py2 = best_box.xyxy[0].cpu().numpy().astype(int)
                    conf = float(best_box.conf[0])
                    pw = max(1, px2 - px1)
                    ph = max(1, py2 - py1)
                    ar = pw / float(ph)

                    plate_crop = vehicle_crop[py1:py2, px1:px2]
                    if plate_crop.size > 0:
                        return PlateDetection(
                            plate_box=[vx1 + px1, vy1 + py1, vx1 + px2, vy1 + py2],
                            vehicle_box=[vx1, vy1, vx2, vy2],
                            confidence=conf,
                            plate_crop=plate_crop,
                            vehicle_crop=vehicle_crop,
                            aspect_ratio=ar,
                            method="YOLO_PLATE_MODEL",
                        )
            except Exception as e:
                logger.debug(f"YOLO plate detection exception: {e}")

        # 2. Tier 2: Adaptive Geometric & Morphological Plate Localizer
        return self._detect_plate_morphological(frame, vehicle_crop, [vx1, vy1, vx2, vy2], vehicle_type)

    def _detect_plate_morphological(
        self,
        frame: np.ndarray,
        vehicle_crop: np.ndarray,
        v_box: List[int],
        vehicle_type: str,
    ) -> Optional[PlateDetection]:
        """Extracts candidate license plate using color-space segmentation, edge filters, and aspect ratio constraints."""
        vx1, vy1, vx2, vy2 = v_box
        vh, vw = vehicle_crop.shape[:2]

        # Indian vehicle plate typical mounting zones:
        # Cars / Buses / Trucks: Lower 45% of vehicle body
        # Motorcycles: Lower 50%
        if vehicle_type in ("car", "bus", "truck"):
            roi_y1 = int(vh * 0.35)
            roi_y2 = int(vh * 0.95)
            roi_x1 = int(vw * 0.10)
            roi_x2 = int(vw * 0.90)
        elif vehicle_type == "motorcycle":
            roi_y1 = int(vh * 0.30)
            roi_y2 = int(vh * 0.95)
            roi_x1 = int(vw * 0.08)
            roi_x2 = int(vw * 0.92)
        else:
            roi_y1 = int(vh * 0.30)
            roi_y2 = int(vh * 0.95)
            roi_x1 = int(vw * 0.10)
            roi_x2 = int(vw * 0.90)

        roi_crop = vehicle_crop[roi_y1:roi_y2, roi_x1:roi_x2]
        if roi_crop.size == 0:
            return None

        rh, rw = roi_crop.shape[:2]
        roi_area = rh * rw

        candidates = []

        # =========================================================================
        # 1. Color Segmentation (White & Yellow Indian License Plates)
        # =========================================================================
        hsv_roi = cv2.cvtColor(roi_crop, cv2.COLOR_BGR2HSV)
        # White plate mask (private cars/bikes)
        white_mask = cv2.inRange(hsv_roi, np.array([0, 0, 130]), np.array([180, 70, 255]))
        # Yellow plate mask (commercial taxis, autos, buses, trucks)
        yellow_mask = cv2.inRange(hsv_roi, np.array([12, 50, 110]), np.array([38, 255, 255]))
        color_mask = cv2.bitwise_or(white_mask, yellow_mask)

        rect_color_k = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        color_closed = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, rect_color_k)
        contours_c, _ = cv2.findContours(color_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours_c:
            x, y, w, h = cv2.boundingRect(cnt)
            if w <= 0 or h <= 0:
                continue
            ar = float(w) / float(h)
            area = w * h
            if 1.8 <= ar <= 6.0 and area >= 300 and area <= 0.45 * roi_area:
                cx = x + w / 2.0
                center_dist = abs(cx - (rw / 2.0)) / float(rw)
                score = (1.0 / (1.0 + abs(ar - 3.5))) * (1.0 - 0.4 * center_dist) * 1.15
                candidates.append((score, [x, y, w, h], "COLOR_SEGMENTATION"))

        # =========================================================================
        # 2. Horizontal Gradient & Sobel Morphological Closing
        # =========================================================================
        gray_roi = cv2.cvtColor(roi_crop, cv2.COLOR_BGR2GRAY)
        grad_x = cv2.Sobel(gray_roi, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
        grad_x = np.absolute(grad_x)
        min_val, max_val = np.min(grad_x), np.max(grad_x)
        if max_val > min_val:
            grad_x = (255 * ((grad_x - min_val) / (max_val - min_val))).astype(np.uint8)
        else:
            grad_x = np.zeros_like(gray_roi)

        blurred = cv2.GaussianBlur(grad_x, (5, 5), 0)
        rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed = cv2.morphologyEx(blurred, cv2.MORPH_CLOSE, rect_kernel)

        _, thresh = cv2.threshold(closed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours_g, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours_g:
            x, y, w, h = cv2.boundingRect(cnt)
            if w <= 0 or h <= 0:
                continue
            ar = float(w) / float(h)
            area = w * h
            if 1.8 <= ar <= 5.8 and area >= 400 and area <= 0.45 * roi_area:
                cx = x + w / 2.0
                center_dist = abs(cx - (rw / 2.0)) / float(rw)
                score = (1.0 / (1.0 + abs(ar - 3.5))) * (1.0 - 0.5 * center_dist)
                candidates.append((score, [x, y, w, h], "SOBEL_GRADIENT"))

        # =========================================================================
        # 3. Select Best Candidate with Padding
        # =========================================================================
        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            best_score, (bx, by, bw, bh), method = candidates[0]

            # Add 8% horizontal and 12% vertical padding around detected plate to avoid character clipping
            pad_x = max(2, int(bw * 0.08))
            pad_y = max(2, int(bh * 0.12))

            plate_fx1 = vx1 + roi_x1 + max(0, bx - pad_x)
            plate_fy1 = vy1 + roi_y1 + max(0, by - pad_y)
            plate_fx2 = vx1 + roi_x1 + min(rw, bx + bw + pad_x)
            plate_fy2 = vy1 + roi_y1 + min(rh, by + bh + pad_y)

            fh, fw = frame.shape[:2]
            p_x1 = max(0, min(fw - 1, plate_fx1))
            p_y1 = max(0, min(fh - 1, plate_fy1))
            p_x2 = max(p_x1 + 1, min(fw, plate_fx2))
            p_y2 = max(p_y1 + 1, min(fh, plate_fy2))

            crop = frame[p_y1:p_y2, p_x1:p_x2]
            if crop.size > 0:
                pw = p_x2 - p_x1
                ph = p_y2 - p_y1
                ar = float(pw) / float(max(1, ph))
                confidence = min(0.95, max(0.40, best_score * 0.95))

                return PlateDetection(
                    plate_box=[p_x1, p_y1, p_x2, p_y2],
                    vehicle_box=[vx1, vy1, vx2, vy2],
                    confidence=confidence,
                    plate_crop=crop,
                    vehicle_crop=vehicle_crop,
                    aspect_ratio=ar,
                    method=f"ADAPTIVE_{method}",
                )

        # Fallback default subregion if no prominent contour passed filters
        default_pw = int(vw * 0.48)
        default_ph = int(vh * 0.16)
        if default_pw > 15 and default_ph > 8:
            px1 = vx1 + int((vw - default_pw) / 2)
            py1 = vy1 + int(vh * 0.65)
            px2 = px1 + default_pw
            py2 = py1 + default_ph

            fh, fw = frame.shape[:2]
            px1 = max(0, min(fw - 1, px1))
            py1 = max(0, min(fh - 1, py1))
            px2 = max(px1 + 1, min(fw, px2))
            py2 = max(py1 + 1, min(fh, py2))

            crop = frame[py1:py2, px1:px2]
            if crop.size > 0:
                return PlateDetection(
                    plate_box=[px1, py1, px2, py2],
                    vehicle_box=[vx1, vy1, vx2, vy2],
                    confidence=0.45,
                    plate_crop=crop,
                    vehicle_crop=vehicle_crop,
                    aspect_ratio=float(px2 - px1) / float(max(1, py2 - py1)),
                    method="GEOMETRIC_FALLBACK",
                )

        return None
