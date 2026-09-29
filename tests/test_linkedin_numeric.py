import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents")))

from linkedin_applier import _numeric_only


def test_numeric_only_strips_units():
    # LinkedIn numeric inputs reject "30 days" → modal validation loop.
    assert _numeric_only("30 days") == "30"
    assert _numeric_only("2.5 years") == "2.5"
    assert _numeric_only("Immediately") == "0"
    assert _numeric_only(None) == "0"
    assert _numeric_only(15) == "15"


def test_identity_helpers():
    from linkedin_applier import _national_phone, _identity_value
    assert _national_phone("+91 98765-43210") == "9876543210"
    assert _national_phone("") == ""
    ident = [(["first name"], "Harsh"), (["phone", "mobile"], "9876543210")]
    assert _identity_value("mobile phone number", ident) == "9876543210"
    assert _identity_value("city", ident) == ""


def test_upload_uses_original_filename(tmp_path):
    from linkedin_applier import _with_original_name
    src = tmp_path / "resume.pdf"
    src.write_bytes(b"%PDF-1.4")
    out = _with_original_name(str(src), "Harsh_Raghuwanshi_Resume.pdf", "u1")
    assert os.path.basename(out) == "Harsh_Raghuwanshi_Resume.pdf"
    assert open(out, "rb").read() == b"%PDF-1.4"
    assert _with_original_name(str(src), None) == str(src)
