"""Live-DOM test for google_form_filler.fill_web_form: generic Lever/Greenhouse-
style form must map each field to the right profile value (no name→company leak)."""
from selenium.webdriver.common.by import By
import google_form_filler as gff

CFG = {"profile": {"full_name": "Asha Rao", "current_company": "Acme",
                   "location": "Bengaluru"}, "email": "asha@example.com"}

def _v(driver, _id):
    return driver.find_element(By.ID, _id).get_attribute("value")

def test_web_form_fields_mapped_correctly(load_fixture):
    driver = load_fixture("webform.html")
    gff.fill_web_form(driver, CFG)
    assert _v(driver, "fn") == "Asha Rao"
    assert _v(driver, "co") != "Asha Rao"      # company field must not get the name
    assert _v(driver, "co") in ("Acme", "")    # company or left blank, never the name
    assert _v(driver, "em") == "asha@example.com"
    assert _v(driver, "ct") == "Bengaluru"
