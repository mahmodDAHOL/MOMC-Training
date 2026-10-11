from datetime import date

from momc_training.ocr import text


def test_arabic_indic_digits_to_latin():
    assert text.to_latin_digits("٠١٢٣٤٥٦٧٨٩٠") == "01234567890"
    assert text.to_latin_digits("۱۲۳") == "123"


def test_clean_strips_tatweel_bidi_and_diacritics():
    assert text.clean("‏الاســــمُ  ") == "الاسم"


def test_clean_name_drops_noise_tokens():
    assert text.clean_name("سامر ض") == "سامر"
    assert text.clean_name('أحمد خليل ّ') == "أحمد خليل"


def test_after_label_removes_leaked_label():
    assert text.after_label("سب الام : هالة يوسف") == "هالة يوسف"
    assert text.after_label("دمشق") == "دمشق"


def test_national_id_validation():
    assert text.valid_national_id("٠١٢٣٤٥٦٧٨٩٠")
    assert not text.valid_national_id("0123456789")
    assert not text.valid_national_id("0123456789a")


def test_visual_date_groups_both_orders():
    assert text.parse_visual_date(["1983", "8", "6"]) == date(1983, 8, 6)
    assert text.parse_visual_date(["22", "04", "2006"]) == date(2006, 4, 22)
    assert text.parse_visual_date(["1983", "13", "6"]) is None
    assert text.parse_visual_date(["83", "8"]) is None
    assert text.parse_visual_date(["1998", "5", "150"]) == date(1998, 5, 15)
    assert text.parse_visual_date(["1976", "6", "1100"]) == date(1976, 6, 11)


def test_split_place_and_date():
    assert text.split_place_and_date("دمشق ٦-٨-١٩٩٩") == ("دمشق", ["6", "8", "1999"])


def test_gender_tolerates_one_wrong_letter():
    assert text.detect_gender("- كثر ا لون الوجه: حنطي") == text.GENDER_MALE
    assert text.detect_gender("الجنس: أنثى") == text.GENDER_FEMALE
    assert text.detect_gender("لون العينين: بني") is None
