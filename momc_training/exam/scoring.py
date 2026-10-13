"""Exam scoring and domain recommendation (pure; no Frappe imports).

Rules (from the programme document):
- pass = total >= pass_total and, when configured, the required section meets
  its threshold.
- domain = the applicant's preference if it meets the threshold; otherwise the
  highest-scoring domain, preferring the applicant's choice on ties.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rules:
    pass_total: float = 50
    pass_section_min: float = 20
    domain_min: float = 10
    pass_section: str | None = None


DEFAULT_RULES = Rules()


@dataclass
class Result:
    by_section: dict[str, float] = field(default_factory=dict)
    max_by_section: dict[str, float] = field(default_factory=dict)
    total: float = 0
    max_total: float = 0
    passed: bool = False
    recommended_domain: str = ""
    correct: int = 0
    answered: int = 0


def score(
    questions: list[dict],
    answers: dict[str, str],
    preference: str = "",
    rules: Rules = DEFAULT_RULES,
    domains: Sequence[str] = (),
) -> Result:
    """questions: [{name, section, correct, points}], answers: {name: "A".."D"}."""
    sections = dict.fromkeys([*domains, *(q["section"] for q in questions)], 0.0)
    res = Result(by_section=sections.copy(), max_by_section=sections.copy())
    for q in questions:
        section = q["section"]
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
    required_score = res.by_section.get(rules.pass_section, 0) if rules.pass_section else 0
    meets_required_section = not rules.pass_section or required_score >= rules.pass_section_min
    res.passed = res.total >= rules.pass_total and meets_required_section
    res.recommended_domain = recommend_domain(res.by_section, preference, domains, rules)
    return res


def recommend_domain(
    by_section: dict[str, float],
    preference: str,
    domains: Sequence[str] = (),
    rules: Rules = DEFAULT_RULES,
) -> str:
    order = list(dict.fromkeys(domains)) if domains else list(by_section)
    if preference in order and by_section.get(preference, 0) >= rules.domain_min:
        return preference
    if not order:
        return ""
    if preference in order:
        order.remove(preference)
        order.insert(0, preference)
    return max(order, key=lambda domain: by_section.get(domain, 0))
