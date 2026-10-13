from momc_training.exam.scoring import Rules, recommend_domain, score

BANK = (
    [{"name": f"g{i}", "section": "General", "correct": "A", "points": 2} for i in range(20)]
    + [{"name": f"o{i}", "section": "Operations", "correct": "B", "points": 2} for i in range(10)]
    + [{"name": f"d{i}", "section": "Data", "correct": "C", "points": 2} for i in range(10)]
    + [{"name": f"p{i}", "section": "Product", "correct": "D", "points": 2} for i in range(10)]
)


def answers(general=0, operations=0, data=0, product=0):
    out = {}
    out.update({f"g{i}": "A" for i in range(general)})
    out.update({f"o{i}": "B" for i in range(operations)})
    out.update({f"d{i}": "C" for i in range(data)})
    out.update({f"p{i}": "D" for i in range(product)})
    return out


def test_full_marks():
    r = score(BANK, answers(20, 10, 10, 10), "Product")
    assert r.total == r.max_total == 100
    assert r.passed and r.recommended_domain == "Product"


def test_wrong_and_blank_score_zero_case_insensitive():
    r = score(BANK, {"g0": "b", "g1": "", "g2": "a"})
    assert r.by_section["General"] == 2 and r.answered == 2 and r.correct == 1


def test_pass_needs_total_and_configured_section():
    rules = Rules(pass_section="General")
    r = score(BANK, answers(9, 10, 10, 1), rules=rules)
    assert r.total == 60 and not r.passed
    r = score(BANK, answers(10, 10, 5, 0), rules=rules)
    assert r.total == 50 and r.passed


def test_preference_kept_when_its_domain_reaches_minimum():
    domains = ["Operations", "Data", "Product"]
    assert recommend_domain({"Operations": 18, "Data": 10, "Product": 4}, "Data", domains) == "Data"


def test_falls_back_to_best_domain_then_preference_on_tie():
    domains = ["Operations", "Data", "Product"]
    assert recommend_domain({"Operations": 18, "Data": 6, "Product": 4}, "Data", domains) == "Operations"
    assert recommend_domain({"Operations": 8, "Data": 8, "Product": 8}, "Product", domains) == "Product"
    assert recommend_domain({"Operations": 8, "Data": 8, "Product": 2}, "", domains) == "Operations"


def test_recommendation_ignores_sections_that_are_not_domains():
    domains = ["Support", "Security", "Programming"]
    result = score(
        [{"name": "q1", "section": "Cybersecurity", "correct": "A", "points": 2}],
        {"q1": "A"},
        "Cybersecurity",
        domains=domains,
    )
    assert result.recommended_domain in domains


def test_custom_rules():
    r = score(
        BANK,
        answers(10, 5, 0, 0),
        "",
        Rules(pass_total=30, pass_section_min=20, domain_min=10, pass_section="General"),
    )
    assert r.passed
