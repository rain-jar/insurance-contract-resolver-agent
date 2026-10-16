from contract_stack.chunking import chunk_blocks
from contract_stack.models import ExtractionMethod, TextBlock


def test_chunking_retains_source_locator() -> None:
    blocks = [
        TextBlock(document_path="a.txt", block_index=i, locator=f"paragraph:{i+1}", text=text, extraction_method=ExtractionMethod.TEXT, page_number=None)
        for i, text in enumerate(["alpha " * 20, "beta " * 20, "gamma " * 20])
    ]
    chunks = chunk_blocks(blocks, target_chars=150, overlap_blocks=1)
    assert len(chunks) >= 2
    assert chunks[0].document_path == "a.txt"
    assert chunks[0].locator.startswith("paragraph:1")


def test_oversized_block_is_emitted_once() -> None:
    block = TextBlock(
        document_path="policy.pdf",
        block_index=0,
        locator="page:1",
        text="contract text " * 500,
        extraction_method=ExtractionMethod.TEXT,
        page_number=1,
    )
    chunks = chunk_blocks([block], target_chars=500, overlap_blocks=1)
    assert len(chunks) == 1
    assert chunks[0].locator == "page:1"
