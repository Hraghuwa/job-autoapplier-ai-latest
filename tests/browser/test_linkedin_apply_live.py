"""End-to-end (machinery) test of the LinkedIn Easy-Apply walk against a faithful
local fixture of LinkedIn's modal. CANNOT touch the live site (no creds / ToS /
login challenge), but exercises the real process_easy_apply_modal: multi-step
Next->Review->Submit, button finding, and submit detection."""
from selenium.webdriver.common.by import By
import linkedin_applier as la

CONFIG = {"profile": {"full_name": "Asha Rao", "email": "asha@example.com",
                      "phone": "+91 90000 11111", "years_of_experience": "2"},
          "email": "asha@example.com", "resume_path": "", "auto_submit": True}

def test_easy_apply_walks_to_submitted(load_fixture):
    driver = load_fixture("linkedin_easyapply.html")
    result = la.process_easy_apply_modal(driver, CONFIG, dry_run=False)
    assert result == "submitted"
    assert "Application submitted" in driver.find_element(By.ID, "result").text

def test_action_button_prefers_submit_over_next(load_fixture):
    # On the final step the helper must pick Submit, not a stray Next.
    driver = load_fixture("linkedin_easyapply.html")
    # advance to step 3 directly
    driver.execute_script("document.getElementById('s1').style.display='none';"
                          "document.getElementById('s3').style.display='block';")
    btn, action = la._find_modal_action_button(driver)
    assert action == "submit"
