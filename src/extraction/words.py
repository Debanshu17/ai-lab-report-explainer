"""Word-coordinate extraction and spatial clustering using PyMuPDF."""

from __future__ import annotations

from typing import List
from pydantic import BaseModel

import pymupdf


class PDFWord(BaseModel):
    """A single word token extracted from a PDF with its bounding box."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int  # 1-indexed


class PDFLine(BaseModel):
    """A horizontal row of words clustered by y-coordinate."""

    words: List[PDFWord]
    y_center: float
    y0: float
    y1: float
    x0: float
    x1: float
    page: int

    @property
    def line_text(self) -> str:
        return " ".join(w.text for w in self.words)


def extract_page_words(page: pymupdf.Page, page_num: int) -> List[PDFWord]:
    """Extract all word tokens with spatial bounding boxes from a single page."""
    raw_words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    words: List[PDFWord] = []

    for w in raw_words:
        if len(w) >= 5:
            text = str(w[4]).strip()
            if text:
                words.append(
                    PDFWord(
                        text=text,
                        x0=float(w[0]),
                        y0=float(w[1]),
                        x1=float(w[2]),
                        y1=float(w[3]),
                        page=page_num,
                    )
                )

    # Sort primarily by vertical coordinate y0, secondarily by horizontal x0
    words.sort(key=lambda item: (item.y0, item.x0))
    return words


def cluster_words_into_lines(words: List[PDFWord], y_tolerance: float = 3.5) -> List[PDFLine]:
    """Cluster words sharing approximately the same vertical baseline into horizontal lines."""
    if not words:
        return []

    lines: List[PDFLine] = []
    current_cluster: List[PDFWord] = [words[0]]

    for w in words[1:]:
        # Compare center y of candidate word with average center y of current cluster
        curr_y_centers = [(item.y0 + item.y1) / 2.0 for item in current_cluster]
        avg_y_center = sum(curr_y_centers) / len(curr_y_centers)
        w_center = (w.y0 + w.y1) / 2.0

        if abs(w_center - avg_y_center) <= y_tolerance and w.page == current_cluster[0].page:
            current_cluster.append(w)
        else:
            # Finalize current cluster sorted horizontally by x0
            current_cluster.sort(key=lambda item: item.x0)
            lines.append(
                PDFLine(
                    words=current_cluster,
                    y_center=avg_y_center,
                    y0=min(item.y0 for item in current_cluster),
                    y1=max(item.y1 for item in current_cluster),
                    x0=min(item.x0 for item in current_cluster),
                    x1=max(item.x1 for item in current_cluster),
                    page=current_cluster[0].page,
                )
            )
            current_cluster = [w]

    if current_cluster:
        current_cluster.sort(key=lambda item: item.x0)
        curr_y_centers = [(item.y0 + item.y1) / 2.0 for item in current_cluster]
        avg_y_center = sum(curr_y_centers) / len(curr_y_centers)
        lines.append(
            PDFLine(
                words=current_cluster,
                y_center=avg_y_center,
                y0=min(item.y0 for item in current_cluster),
                y1=max(item.y1 for item in current_cluster),
                x0=min(item.x0 for item in current_cluster),
                x1=max(item.x1 for item in current_cluster),
                page=current_cluster[0].page,
            )
        )

    return lines
