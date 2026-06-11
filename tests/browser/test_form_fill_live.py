"""Live-DOM tests: run the real smart_form_filler against HTML fixtures.

Catches selector bugs that pure tests can't — notably the label-leak that filled
email/phone with the candidate's NAME because the field's label aggregation
pulled in the *previous* field's <label> via a greedy preceding-label XPath.
"""
from selenium.webdriver.common.by import By

import smart_form_filler as sff

CONFIG = {
    "profile": {
        "full_name": "Asha Rao",
        "phone": "+91 90000 11111",
        "linkedin": "https://linkedin.com/in/asha",
    },
    "email": "asha@example.com",
    "cover_letter": "I want to build reliable backend systems with your team.",
}


def _val(driver, _id):
    return driver.find_element(By.ID, _id).get_attribute("value")


def test_stacked_form_maps_each_field_correctly(load_fixture):
    driver = load_fixture("stacked_form.html")
    sff.fill_all_form_fields(driver, CONFIG)

    # The bug this guards against: email/phone/linkedin getting the NAME because
    # the previous field's label leaked into the current field's label text.
    assert _val(driver, "fullname") == "Asha Rao"
    assert _val(driver, "email") == "asha@example.com"
    assert _val(driver, "phone") == "+91 90000 11111"
    assert _val(driver, "linkedin") == "https://linkedin.com/in/asha"
    assert "build reliable backend" in _val(driver, "why")


def test_no_field_filled_with_the_name_by_mistake(load_fixture):
    driver = load_fixture("stacked_form.html")
    sff.fill_all_form_fields(driver, CONFIG)
    # Only the name field may contain the name.
    for fid in ("email", "phone", "linkedin", "why"):
        assert _val(driver, fid) != "Asha Rao", f"{fid} was wrongly filled with the name"


def test_label_extraction_does_not_leak_previous_label(load_fixture):
    driver = load_fixture("stacked_form.html")
    email_el = driver.find_element(By.ID, "email")
    label = sff._get_field_label(driver, email_el)
    assert "email" in label
    assert "full name" not in label, f"previous label leaked into: {label!r}"


def test_labelless_div_form_maps_via_container_fallback(load_fixture):
    # No <label> elements — labels live in sibling <div>s. The container-scoped
    # fallback must still map each field correctly without cross-field leakage.
    driver = load_fixture("labelless_div_form.html")
    sff.fill_all_form_fields(driver, CONFIG)
    assert _val(driver, "a") == "Asha Rao"
    assert _val(driver, "b") == "asha@example.com"
    assert _val(driver, "c") == "+91 90000 11111"
