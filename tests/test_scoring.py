from momc_training.exam.scoring import Rules, recommend_track, score

BANK = (
    [{"name": f"a{i}", "section": "Aptitude", "correct": "A", "points": 2} for i in range(20)]
    + [{"name": f"s{i}", "section": "Support", "correct": "B", "points": 2} for i in range(10)]
    + [{"name": f"c{i}", "section": "Security", "correct": "C", "points": 2} for i in range(10)]
    + [{"name": f"p{i}", "section": "Programming", "correct": "D", "points": 2} for i in range(10)]
)


def answers(apt=0, sup=0, sec=0, prog=0):
    out = {}
    out.update({f"a{i}": "A" for i in range(apt)})
    out.update({f"s{i}": "B" for i in range(sup)})
    out.update({f"c{i}": "C" for i in range(sec)})
    out.update({f"p{i}": "D" for i in range(prog)})
    return out


def test_full_marks():
    r = score(BANK, answers(20, 10, 10, 10), "Programming")
    assert r.total == r.max_total == 100
    assert r.passed and r.recommended_track == "Programming"


def test_wrong_and_blank_score_zero_case_insensitive():
    r = score(BANK, {"a0": "b", "a1": "", "a2": "a"})
    assert r.by_section["Aptitude"] == 2 and r.answered == 2 and r.correct == 1


def test_pass_needs_total_and_aptitude():
    # 60 total but aptitude 18 (< 20) -> fails
    r = score(BANK, answers(9, 10, 10, 1))
    assert r.total == 60 and not r.passed
    r = score(BANK, answers(10, 10, 5, 0))
    assert r.total == 50 and r.passed


def test_preference_kept_when_its_section_reaches_minimum():
    assert recommend_track({"Support": 18, "Security": 10, "Programming": 4}, "Cybersecurity") == "Cybersecurity"


def test_falls_back_to_best_section_then_preference_on_tie():
    assert recommend_track({"Support": 18, "Security": 6, "Programming": 4}, "Cybersecurity") == "IT End User Support"
    assert recommend_track({"Support": 8, "Security": 8, "Programming": 8}, "Programming") == "Programming"
    assert recommend_track({"Support": 8, "Security": 8, "Programming": 2}, "") == "IT End User Support"


def test_custom_rules():
    r = score(BANK, answers(10, 5, 0, 0), "", Rules(pass_total=30, pass_aptitude=20, track_min=10))
    assert r.passed
