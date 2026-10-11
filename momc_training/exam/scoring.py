"""Exam scoring and track recommendation (pure; no Frappe imports).

Rules (from the programme document):
- pass = total >= pass_total AND aptitude >= pass_aptitude
- track = the applicant's preference if their score in that track's section
  is >= track_min; otherwise the track whose section they scored highest in
  (ties go to the preference, then to the order below).
"""

from __future__ import annotations

from dataclasses import dataclass, field

SECTIONS = ("Aptitude", "Support", "Security", "Programming")
TRACK_SECTION = {
    "IT End User Support": "Support",
    "Cybersecurity": "Security",
    "Programming": "Programming",
}
TRACKS = tuple(TRACK_SECTION)


@dataclass(frozen=True)
class Rules:
    pass_total: float = 50
    pass_aptitude: float = 20
    track_min: float = 10


DEFAULT_RULES = Rules()


@dataclass
class Result:
    by_section: dict[str, float] = field(default_factory=dict)
    max_by_section: dict[str, float] = field(default_factory=dict)
    total: float = 0
    max_total: float = 0
    passed: bool = False
    recommended_track: str = ""
    correct: int = 0
    answered: int = 0


def score(questions: list[dict], answers: dict[str, str], preference: str = "", rules: Rules = DEFAULT_RULES) -> Result:
    """questions: [{name, section, correct, points}], answers: {name: "A".."D"}."""
    res = Result(by_section={s: 0.0 for s in SECTIONS}, max_by_section={s: 0.0 for s in SECTIONS})
    for q in questions:
        section = q["section"]
        if section not in res.by_section:
            continue
        points = float(q.get("points") or 0)
        res.max_by_section[section] += points
        given = (answers.get(q["name"]) or "").strip().upper()
        if given:
            res.answered += 1
        if given and given == str(q["correct"]).strip().upper():
            res.by_section[section] += points
            res.correct += 1
    res.total = sum(res.by_section.values())
    res.max_total = sum(res.max_by_section.values())
    res.passed = res.total >= rules.pass_total and res.by_section["Aptitude"] >= rules.pass_aptitude
    res.recommended_track = recommend_track(res.by_section, preference, rules)
    return res


def recommend_track(by_section: dict[str, float], preference: str, rules: Rules = DEFAULT_RULES) -> str:
    if preference in TRACK_SECTION and by_section.get(TRACK_SECTION[preference], 0) >= rules.track_min:
        return preference
    order = ([preference] if preference in TRACK_SECTION else []) + [t for t in TRACKS if t != preference]
    return max(order, key=lambda t: (by_section.get(TRACK_SECTION[t], 0), -order.index(t)))
