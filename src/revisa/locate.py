"""Find the title block from OCR lines (ADR 0004).

Lines containing title-block vocabulary are anchors. Anchors close to each other form clusters;
the densest cluster is the title block's core, and the region grows from there to the adjacent
text. Distances scale with the page size, so the same settings work at any resolution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from revisa.ocr import Box, Line


@dataclass(frozen=True)
class LocateConfig:
    keywords: re.Pattern[str]
    ignore: re.Pattern[str]  # text that looks relevant but never belongs to the block
    cluster_gap: float = 0.08  # anchors within this fraction of the page diagonal join a cluster
    grow_gap: float = 0.025  # lines within this fraction of the diagonal join the region
    pad: float = 0.01  # padding around the final region, fraction of the diagonal
    max_area: float = 0.5  # a "title block" covering more of the page than this is rejected


@dataclass(frozen=True)
class Region:
    box: Box
    anchors: tuple[Line, ...]  # the keyword lines that placed the region; shown to reviewers
    lines: tuple[Line, ...]  # every OCR line inside the region


def locate(lines: list[Line], width: float, height: float, config: LocateConfig) -> Region | None:
    diagonal = (width * width + height * height) ** 0.5
    candidates = [ln for ln in lines if not config.ignore.search(ln.text)]
    anchors = [ln for ln in candidates if config.keywords.search(ln.text)]
    if not anchors:
        return None

    core = max(_clusters(anchors, config.cluster_gap * diagonal), key=_cluster_rank)
    box = core[0].box
    for anchor in core[1:]:
        box = box.union(anchor.box)

    members = set(core)
    grew = True
    while grew:
        grew = False
        for line in candidates:
            if line not in members and box.gap_to(line.box) <= config.grow_gap * diagonal:
                members.add(line)
                box = box.union(line.box)
                grew = True

    if box.width * box.height > config.max_area * width * height:
        return None
    padded = box.padded(config.pad * diagonal, width, height)
    inside = tuple(ln for ln in candidates if ln in members)
    return Region(box=padded, anchors=tuple(core), lines=inside)


def _clusters(anchors: list[Line], gap: float) -> list[list[Line]]:
    """Single-linkage clustering: anchors closer than ``gap`` (directly or via others) group."""
    clusters: list[list[Line]] = []
    for anchor in anchors:
        joined = [c for c in clusters if any(anchor.box.gap_to(other.box) <= gap for other in c)]
        merged = [anchor] + [line for c in joined for line in c]
        clusters = [c for c in clusters if c not in joined] + [merged]
    return clusters


def _cluster_rank(cluster: list[Line]) -> tuple[int, float]:
    # Most anchors wins; ties go to the cluster lower and further right, where title blocks
    # conventionally sit.
    corner = max(line.box.x1 + line.box.y1 for line in cluster)
    return (len(cluster), corner)
