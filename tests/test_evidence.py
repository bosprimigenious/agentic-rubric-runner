"""测试：Evidence Pack 抽取。"""

from pathlib import Path

from aarrr_agent.evidence import extract_evidence_pack, format_evidence_for_prompt, save_evidence_pack


def test_extract_evidence_pack_from_fixture():
    pdf = Path("fixtures/attachment.pdf")
    if not pdf.exists():
        return
    pack = extract_evidence_pack(str(pdf), max_facts=10)
    assert pack.facts
    assert pack.facts[0].id.startswith("E")
    assert pack.facts[0].page >= 1
    text = format_evidence_for_prompt(pack)
    assert "E01" in text


def test_save_and_load_roundtrip(tmp_path):
    pdf = Path("fixtures/attachment.pdf")
    if not pdf.exists():
        return
    pack = extract_evidence_pack(str(pdf), max_facts=5)
    out = tmp_path / "evidence_pack.json"
    save_evidence_pack(pack, out)
    assert out.exists()
    loaded = __import__("aarrr_agent.evidence", fromlist=["load_evidence_pack"]).load_evidence_pack(out)
    assert len(loaded.facts) == len(pack.facts)
