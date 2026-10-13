import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from momc_training.api import files
from momc_training.utils.uploads import UploadRejected


def endpoint():
    # Skip the HTTP rate-limit/whitelist wrappers and exercise the endpoint body.
    return files.upload.__wrapped__.__wrapped__


def prepare_upload(monkeypatch, data=b"original", max_mb=2):
    stream = Mock(wraps=io.BytesIO(data))
    request = SimpleNamespace(files={"file": SimpleNamespace(stream=stream)})
    monkeypatch.setattr(files.frappe, "request", request, raising=False)
    monkeypatch.setattr(files, "_", lambda message: message)
    monkeypatch.setattr(files.session, "require", Mock(return_value="APPLICANT-1"))
    monkeypatch.setattr(
        files.frappe,
        "get_cached_doc",
        Mock(return_value=SimpleNamespace(max_upload_mb=max_mb)),
    )

    def throw(message, *args, **kwargs):
        raise ValueError(message)

    monkeypatch.setattr(files.frappe, "throw", Mock(side_effect=throw))
    return stream


def test_upload_stores_sanitised_file_and_returns_ocr(monkeypatch):
    stream = prepare_upload(monkeypatch)
    doc = SimpleNamespace(name="APPLICANT-1")
    sanitise = Mock(return_value=(b"clean image", "jpg"))
    replace_file = Mock()
    ocr = {"status": "ok", "side": "front", "fields": {"name": "Ali"}}
    run_ocr = Mock(return_value=ocr)
    monkeypatch.setattr(files, "sanitise", sanitise)
    monkeypatch.setattr(files, "_editable", Mock(return_value=doc))
    monkeypatch.setattr(files, "_replace_file", replace_file)
    monkeypatch.setattr(files, "_run_ocr", run_ocr)

    result = endpoint()(kind="id_front")

    stream.read.assert_called_once_with(2 * 1024 * 1024 + 1)
    sanitise.assert_called_once_with(b"original", "id_front", 2 * 1024 * 1024)
    replace_file.assert_called_once_with(doc, "id_front", b"clean image", "jpg")
    run_ocr.assert_called_once_with(doc, "id_front", b"clean image")
    assert result == {"kind": "id_front", "uploaded": True, "ocr": ocr}


def test_upload_accepts_cv_kind(monkeypatch):
    prepare_upload(monkeypatch)
    doc = SimpleNamespace(name="APPLICANT-1")
    sanitise = Mock(return_value=(b"clean PDF", "pdf"))
    replace_file = Mock()
    run_ocr = Mock()
    monkeypatch.setattr(files, "sanitise", sanitise)
    monkeypatch.setattr(files, "_editable", Mock(return_value=doc))
    monkeypatch.setattr(files, "_replace_file", replace_file)
    monkeypatch.setattr(files, "_run_ocr", run_ocr)

    result = endpoint()(kind="cv")

    sanitise.assert_called_once_with(b"original", "cv", 2 * 1024 * 1024)
    replace_file.assert_called_once_with(doc, "cv", b"clean PDF", "pdf")
    run_ocr.assert_not_called()
    assert result == {"kind": "cv", "uploaded": True}


def test_upload_rejects_unknown_kind_before_reading_file(monkeypatch):
    stream = prepare_upload(monkeypatch)

    with pytest.raises(ValueError):
        endpoint()(kind="unknown")

    stream.read.assert_not_called()
    files.frappe.throw.assert_called_once()


def test_upload_requires_file(monkeypatch):
    prepare_upload(monkeypatch)
    files.frappe.request.files = {}

    with pytest.raises(ValueError):
        endpoint()(kind="photo")

    files.frappe.throw.assert_called_once()


def test_upload_reports_sanitising_rejection_without_storing(monkeypatch):
    prepare_upload(monkeypatch)
    replace_file = Mock()
    monkeypatch.setattr(files, "sanitise", Mock(side_effect=UploadRejected("invalid file")))
    monkeypatch.setattr(files, "_replace_file", replace_file)

    with pytest.raises(ValueError, match="invalid file"):
        endpoint()(kind="photo")

    replace_file.assert_not_called()
    files.frappe.throw.assert_called_once_with("invalid file")
