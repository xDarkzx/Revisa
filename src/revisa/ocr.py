"""OCR engines behind one interface: text lines with pixel boxes.

``RapidOcrEngine`` runs locally (ONNX, CPU). ``AzureReadEngine`` uses Azure Document Intelligence
``prebuilt-read``. Both return the same ``Line`` objects in the input image's pixel coordinates,
so everything downstream is engine-agnostic (ADR 0006).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.identity import DefaultAzureCredential
from PIL import Image
from rapidocr import RapidOCR


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @classmethod
    def around(cls, points: list[tuple[float, float]]) -> Box:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return cls(min(xs), min(ys), max(xs), max(ys))

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def union(self, other: Box) -> Box:
        return Box(
            min(self.x0, other.x0), min(self.y0, other.y0), max(self.x1, other.x1), max(self.y1, other.y1)
        )

    def gap_to(self, other: Box) -> float:
        """Shortest distance between the two boxes; 0 when they overlap."""
        dx = max(other.x0 - self.x1, self.x0 - other.x1, 0.0)
        dy = max(other.y0 - self.y1, self.y0 - other.y1, 0.0)
        return float((dx * dx + dy * dy) ** 0.5)

    def padded(self, pad: float, width: float, height: float) -> Box:
        return Box(
            max(0.0, self.x0 - pad),
            max(0.0, self.y0 - pad),
            min(width, self.x1 + pad),
            min(height, self.y1 + pad),
        )

    def offset(self, dx: float, dy: float) -> Box:
        return Box(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)


@dataclass(frozen=True)
class Line:
    text: str
    box: Box
    confidence: float


class OcrEngine(Protocol):
    name: str

    def read(self, image: Image.Image) -> list[Line]: ...


class RapidOcrEngine:
    name = "rapidocr"

    def __init__(self, max_side: int = 2400) -> None:
        self._engine = RapidOCR(params={"Det.limit_side_len": max_side, "Det.limit_type": "max"})

    def read(self, image: Image.Image) -> list[Line]:
        # RapidOCR's return type is a union over its pipeline stages; full OCR returns RapidOCROutput.
        result: Any = self._engine(np.asarray(image.convert("RGB")))
        if result.txts is None:
            return []
        return [
            Line(
                text=str(text),
                box=Box.around([(float(x), float(y)) for x, y in box]),
                confidence=float(score),
            )
            for text, box, score in zip(result.txts, result.boxes, result.scores, strict=True)
        ]


class AzureReadEngine:
    """Azure Document Intelligence ``prebuilt-read``, authenticated with Entra ID (ADR 0005)."""

    name = "azure-read"

    def __init__(self, endpoint: str, client: Any | None = None) -> None:
        if client is None:
            client = DocumentIntelligenceClient(endpoint, DefaultAzureCredential())
        self._client = client

    def read(self, image: Image.Image) -> list[Line]:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "PNG")
        buffer.seek(0)
        poller = self._client.begin_analyze_document(
            "prebuilt-read", body=buffer, content_type="application/octet-stream"
        )
        return lines_from_analyze_result(poller.result().as_dict())


def lines_from_analyze_result(result: dict[str, Any]) -> list[Line]:
    """Convert a ``prebuilt-read`` result. For images, polygons are already in pixels."""
    lines = []
    for page in result.get("pages", []):
        if page.get("unit", "pixel") != "pixel":
            raise ValueError(f"expected pixel units for image input, got {page.get('unit')!r}")
        words = page.get("words", [])
        for line in page.get("lines", []):
            polygon = line["polygon"]
            points = [(float(polygon[i]), float(polygon[i + 1])) for i in range(0, len(polygon), 2)]
            lines.append(
                Line(text=line["content"], box=Box.around(points), confidence=_line_confidence(line, words))
            )
    return lines


def _line_confidence(line: dict[str, Any], words: list[dict[str, Any]]) -> float:
    """Document Intelligence scores words, not lines; use the weakest word in the line."""
    spans = line.get("spans", [])
    scores = [
        float(w["confidence"])
        for w in words
        if any(s["offset"] <= w["span"]["offset"] < s["offset"] + s["length"] for s in spans)
    ]
    return min(scores) if scores else 1.0


def lines_to_json(lines: list[Line]) -> list[dict[str, Any]]:
    return [
        {"text": ln.text, "box": [ln.box.x0, ln.box.y0, ln.box.x1, ln.box.y1], "confidence": ln.confidence}
        for ln in lines
    ]


def lines_from_json(data: list[dict[str, Any]]) -> list[Line]:
    return [Line(text=d["text"], box=Box(*d["box"]), confidence=d["confidence"]) for d in data]
