"""
TDD tests for resume upload label checking.
"""

import sys
import os
from unittest.mock import MagicMock, patch

# Ensure the root folder is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents")))

import google_form_filler
import smart_form_filler

def test_google_form_filler_resume_upload_checking(tmp_path):
    # Create a dummy resume
    dummy_resume = tmp_path / "resume.pdf"
    dummy_resume.write_text("dummy resume content")
    resume_path = str(dummy_resume)

    config = {
        "resume_path": resume_path,
        "profile": {}
    }

    # Mock driver and elements
    driver = MagicMock()
    
    # Mock inputs
    fi_resume = MagicMock()
    fi_resume.is_displayed.return_value = True
    fi_resume.get_attribute.side_effect = lambda attr: "resume_field" if attr == "id" else ""
    
    fi_photo = MagicMock()
    fi_photo.is_displayed.return_value = True
    fi_photo.get_attribute.side_effect = lambda attr: "photo_field" if attr == "id" else ""

    driver.find_elements.return_value = [fi_resume, fi_photo]

    # Mock _combined_label
    def mock_get_label(d, element):
        if element == fi_resume:
            return "Resume/CV"
        if element == fi_photo:
            return "Upload Photo"
        return ""

    with patch("google_form_filler._combined_label", side_effect=mock_get_label), \
         patch("os.path.exists", return_value=True):
        # We call fill_web_form (which executes the upload resume block)
        # We need to mock other find_elements calls to avoid errors
        driver.find_elements.side_effect = lambda by, sel: [fi_resume, fi_photo] if "file" in sel else []
        google_form_filler.fill_web_form(driver, config)

    # Assert that resume was uploaded to fi_resume but NOT to fi_photo
    fi_resume.send_keys.assert_called_once_with(resume_path)
    fi_photo.send_keys.assert_not_called()


def test_smart_form_filler_resume_upload_checking(tmp_path):
    dummy_resume = tmp_path / "resume.pdf"
    dummy_resume.write_text("dummy resume content")
    resume_path = str(dummy_resume)

    config = {
        "resume_path": resume_path,
        "profile": {}
    }

    driver = MagicMock()
    
    fi_resume = MagicMock()
    fi_resume.get_attribute.side_effect = lambda attr: "resume_field" if attr == "id" else ""
    
    fi_photo = MagicMock()
    fi_photo.get_attribute.side_effect = lambda attr: "photo_field" if attr == "id" else ""

    # Mock get_field_label
    def mock_get_label(d, element):
        if element == fi_resume:
            return "Resume/CV"
        if element == fi_photo:
            return "Upload Photo"
        return ""

    with patch("smart_form_filler._get_field_label", side_effect=mock_get_label), \
         patch("os.path.exists", return_value=True):
        driver.find_elements.side_effect = lambda by, sel: [fi_resume, fi_photo] if "file" in sel else []
        smart_form_filler.upload_resume(driver, config)

    # Assert that resume was uploaded to fi_resume but NOT to fi_photo
    fi_resume.send_keys.assert_called_once_with(resume_path)
    fi_photo.send_keys.assert_not_called()
