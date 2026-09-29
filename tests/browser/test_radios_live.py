"""Live-DOM tests for fill_radio_buttons: work-auth yes / sponsorship no."""
from selenium.webdriver.common.by import By
import smart_form_filler as sff

def _checked(driver, name):
    for r in driver.find_elements(By.CSS_SELECTOR, f"input[name='{name}']"):
        if r.is_selected():
            return r.get_attribute("value")
    return None

def test_work_authorization_radio_yes(load_fixture):
    driver = load_fixture("radios.html")
    sff.fill_radio_buttons(driver)
    assert _checked(driver, "auth") == "yes"

def test_sponsorship_radio_no(load_fixture):
    driver = load_fixture("radios.html")
    sff.fill_radio_buttons(driver)
    assert _checked(driver, "spon") == "no"
