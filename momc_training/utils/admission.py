EXAM_STUDY_FIELD = "كلية الهندسة المعلوماتية"


def requires_exam(study_field: str | None) -> bool:
    return study_field == EXAM_STUDY_FIELD
