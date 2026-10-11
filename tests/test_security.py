from momc_training.utils import security


def test_dummy_verify_runs():
    security.dummy_verify()


def test_password_policy():
    assert security.password_problem("short1") is not None
    assert security.password_problem("onlyletterslong") is not None
    assert security.password_problem("1234567890") is not None
    assert security.password_problem("mustafa2026xx", "mustafa@momc.gov.sy") is not None
    assert security.password_problem("كلمةسر2026قوية") is None
    assert security.password_problem("Graduate2026") is None


def test_otp_and_tokens():
    codes = {security.new_otp() for _ in range(50)}
    assert all(len(c) == 6 and c.isdigit() for c in codes) and len(codes) > 40
    assert len(security.new_token()) >= 40


def test_digest_is_keyed_and_deterministic():
    a = security.digest("k1", "verify", "x@y.sy", "123456")
    assert a == security.digest("k1", "verify", "x@y.sy", "123456")
    assert a != security.digest("k2", "verify", "x@y.sy", "123456")
    assert a != security.digest("k1", "reset", "x@y.sy", "123456")


def test_email_normalisation():
    assert security.normalise_email("  Ali.Hasan@Example.SY ") == "ali.hasan@example.sy"
    assert security.normalise_email("not-an-email") == ""
    assert security.normalise_email("a@b") == ""
