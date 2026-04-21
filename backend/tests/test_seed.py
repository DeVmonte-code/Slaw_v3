import json
from pathlib import Path

from swiss_legal_api.schemas import Entitlement


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_law_articles_parse():
    data = json.loads((_root() / "seed" / "law_articles.json").read_text())
    assert isinstance(data, list) and len(data) >= 20
    for row in data:
        assert {"sr_number", "article", "language", "text"} <= row.keys()


def test_entitlements_parse_and_count():
    data = json.loads((_root() / "seed" / "entitlements.json").read_text())
    assert len(data) == 15
    ids = set()
    for row in data:
        e = Entitlement.model_validate(row)
        ids.add(e.id)
    assert "rent_reduction_reference_rate" in ids
    assert "childcare_cost_deduction" in ids


def test_entitlement_citations_exist_in_corpus():
    articles = json.loads((_root() / "seed" / "law_articles.json").read_text())
    available = {(a["sr_number"], a["article"]) for a in articles}
    entitlements = json.loads((_root() / "seed" / "entitlements.json").read_text())
    for row in entitlements:
        for cit in row["source_citations"]:
            assert (cit["sr_number"], cit["article"]) in available, (
                f"Entitlement {row['id']} cites missing article "
                f"SR {cit['sr_number']} Art. {cit['article']}"
            )
