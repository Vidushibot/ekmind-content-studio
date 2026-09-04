from pathlib import Path

import fitz


root = Path(__file__).resolve().parent
pdf_path = root / "storage" / "docx_qa" / "Ekmind_AI_Content_Studio_Project_Document.pdf"
output_dir = pdf_path.parent
document = fitz.open(pdf_path)
matrix = fitz.Matrix(1.6, 1.6)
for index, page in enumerate(document, start=1):
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    pixmap.save(output_dir / f"page-{index}.png")
print(f"Rendered {len(document)} pages")
