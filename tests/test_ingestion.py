from pathlib import Path

from contract_stack.ingestion import DocumentIngestor, is_usable_pdf_text
from contract_stack.models import ExtractionMethod


def test_txt_ingestion_preserves_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / "endorsement.txt"
    path.write_text("Endorsement 8\nLimit USD 5,000,000.\n\nAll else unchanged.")
    blocks = DocumentIngestor().ingest(path, "endorsement.txt")
    assert [block.locator for block in blocks] == ["paragraph:1", "paragraph:2"]
    assert blocks[0].extraction_method == ExtractionMethod.TEXT


def test_html_ingestion_preserves_table_row_text(tmp_path: Path) -> None:
    path = tmp_path / "policy.html"
    path.write_text("<html><body><h2>Item 2</h2><table><tr><td>On Premises</td><td>$5,000,000</td></tr></table></body></html>")
    blocks = DocumentIngestor().ingest(path, "policy.html")
    assert [block.text for block in blocks] == ["Item 2", "On Premises $5,000,000"]
    assert all(block.extraction_method == ExtractionMethod.HTML for block in blocks)


def test_pdf_text_quality_rejects_empty_and_cid_gibberish() -> None:
    assert not is_usable_pdf_text("")
    assert not is_usable_pdf_text(" ".join(["(cid:12)"] * 20))
    assert is_usable_pdf_text("Endorsement 7 deletes and restates Item 2 with a $4,250,000 limit." * 2)
