"""Live-DOM tests for fill_checkboxes: must check consent/terms to submit, but
must NOT blindly tick marketing opt-ins or negative 'I do not...' boxes."""
from selenium.webdriver.common.by import By
import smart_form_filler as sff

def _checked(driver, _id):
    return driver.find_element(By.ID, _id).is_selected()

def test_terms_and_privacy_are_checked(load_fixture):
    driver = load_fixture("checkboxes.html")
    sff.fill_checkboxes(driver)
    assert _checked(driver, "terms")
    assert _checked(driver, "privacy")

def test_marketing_optin_not_checked(load_fixture):
    driver = load_fixture("checkboxes.html")
    sff.fill_checkboxes(driver)
    assert not _checked(driver, "news"), "blindly opted into marketing email"

def test_negative_consent_not_checked(load_fixture):
    driver = load_fixture("checkboxes.html")
    sff.fill_checkboxes(driver)
    assert not _checked(driver, "nodata"), "checked an 'I do NOT consent' box"
