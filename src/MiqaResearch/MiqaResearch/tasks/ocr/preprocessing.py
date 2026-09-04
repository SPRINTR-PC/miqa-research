from pathlib import Path

import cv2
import numpy as np
import pymupdf


def convert_pdf_to_image(pdf_path: Path):
    """
    Converts a PDF file to a list of image files
    """
    doc = pymupdf.open(pdf_path)
    return [page.get_pixmap(dpi=300) for page in doc]


def pixmap_to_gray(pixmap: pymupdf.Pixmap) -> np.ndarray:
    """Shared by field_matching (#47) and mark_detection (#48) so both stages
    convert the same rendered page the same way."""
    array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
    if pixmap.n >= 3:
        return cv2.cvtColor(array[:, :, :3], cv2.COLOR_RGB2GRAY)
    return array[:, :, 0]


def load_pages(prom_data) -> list[pymupdf.Pixmap]:
    """Loads a PromData upload as a list of per-page 300 DPI pixmaps.

    PDFs are rasterized page-by-page via convert_pdf_to_image; a plain image
    upload passes through as a single-page list.
    """
    file_path = Path(prom_data.prom_form_file.path)
    if file_path.suffix.lower() == ".pdf":
        return convert_pdf_to_image(file_path)
    return [pymupdf.Pixmap(str(file_path))]
