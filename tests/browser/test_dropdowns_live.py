"""Live-DOM tests for fill_dropdowns: work-authorization logic, country, and
substring false-positives (e.g. 'exp' matching 'expected salary')."""
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
import smart_form_filler as sff

CONFIG = {"profile": {"location": "India"}, "email": "a@b.com"}

def _sel(driver, _id):
    return Select(driver.find_element(By.ID, _id)).first_selected_option.text.strip()

def test_work_authorization_says_yes(load_fixture):
    driver = load_fixture("dropdowns.html")
    sff.fill_dropdowns(driver, CONFIG)
    assert _sel(driver, "auth") == "Yes"

def test_sponsorship_says_no(load_fixture):
    driver = load_fixture("dropdowns.html")
    sff.fill_dropdowns(driver, CONFIG)
    assert _sel(driver, "spon") == "No"

def test_country_picks_india(load_fixture):
    driver = load_fixture("dropdowns.html")
    sff.fill_dropdowns(driver, CONFIG)
    assert _sel(driver, "country") == "India"

def test_expected_salary_not_filled_with_experience_range(load_fixture):
    # The bug: 'expected salary' matched the experience branch ('exp' ⊂ 'expected')
    # and got a years range like '1-3'. Correct: never fill a salary dropdown with
    # an experience value (leaving it for the user beats understating their ask).
    driver = load_fixture("dropdowns.html")
    sff.fill_dropdowns(driver, CONFIG)
    chosen = _sel(driver, "esal")
    assert chosen not in ("0-1", "1-3", "3-5", "5+"), f"salary got an experience range: {chosen}"


def test_experience_dropdown_still_filled(load_fixture):
    # Regression guard: the real experience dropdown must still be matched.
    driver = load_fixture("dropdowns.html")
    sff.fill_dropdowns(driver, CONFIG)
    assert _sel(driver, "exp") in ("1-3", "3-5")
