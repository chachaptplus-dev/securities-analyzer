import fitz  # PyMuPDF
from pathlib import Path


def extract_text_from_pdf(pdf_path: str) -> dict:
    doc = fitz.open(pdf_path)
    pages = []
    full_text = ""

    for page_num, page in enumerate(doc):
        text = page.get_text()
        pages.append({"page": page_num + 1, "text": text})
        full_text += text + "\n"

    metadata = doc.metadata
    doc.close()

    return {
        "path": str(pdf_path),
        "filename": Path(pdf_path).name,
        "pages": pages,
        "full_text": full_text,
        "metadata": metadata,
        "page_count": len(pages),
    }
