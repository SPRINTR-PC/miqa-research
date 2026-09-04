from pathlib import Path

import pymupdf


def convert_pdf_to_image(pdf_path: Path):
    """
    Converts a PDF file to a list of image files
    """
    doc = pymupdf.open(pdf_path)
    return [page.get_pixmap(dpi=300) for page in doc]


def load_pages(prom_data) -> list[pymupdf.Pixmap]:
    """Loads a PromData upload as a list of per-page 300 DPI pixmaps.

    PDFs are rasterized page-by-page via convert_pdf_to_image; a plain image
    upload passes through as a single-page list.
    """
    file_path = Path(prom_data.prom_form_file.path)
    if file_path.suffix.lower() == ".pdf":
        return convert_pdf_to_image(file_path)
    return [pymupdf.Pixmap(str(file_path))]
