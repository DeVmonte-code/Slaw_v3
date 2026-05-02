import json
from pathlib import Path

from swiss_legal_api.schemas import Entitlement


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_law_articles_parse():
    data = json.loads((_root() / "seed" / "law_articles.json").read_text())
    assert isinstance(data, list) and len(data) >= 20
    for row in data:
        # Anti-hallucination guardrail (Task #18): every chunk must carry the
        # canton and effective_date fields the retrieval filter relies on.
        assert {
            "sr_number", "article", "language", "text",
            "canton", "effective_date",
        } <= row.keys(), f"missing required keys in {row}"
        assert row["canton"] == "CH" or len(row["canton"]) == 2
        # ISO date 'YYYY-MM-DD' (validated downstream by the seeder).
        eff = row["effective_date"]
        assert isinstance(eff, str) and len(eff) >= 10
        # repealed_date is optional in the JSON shape but, when present,
        # must be either null or an ISO date string.
        if "repealed_date" in row and row["repealed_date"] is not None:
            assert isinstance(row["repealed_date"], str)


def test_entitlements_parse_and_count():
    data = json.loads((_root() / "seed" / "entitlements.json").read_text())
    # 15 baseline + 3 permit-status sprint additions =
    # quellensteuer_subsequent_assessment, naturalisation_eligibility,
    # family_reunification_right.
    assert len(data) == 18
    ids = set()
    for row in data:
        e = Entitlement.model_validate(row)
        ids.add(e.id)
    assert "rent_reduction_reference_rate" in ids
    assert "childcare_cost_deduction" in ids
    assert "quellensteuer_subsequent_assessment" in ids
    assert "naturalisation_eligibility" in ids
    assert "family_reunification_right" in ids


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
