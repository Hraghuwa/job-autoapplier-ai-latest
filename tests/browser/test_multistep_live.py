"""Live-DOM: walk_multi_step_form drives Next->Submit to completion, and the fit
gate vetoes a clearly-bad (unpaid) posting before any apply."""
import smart_form_filler as sff

PROFILE = {"profile": {"full_name": "Asha Rao", "skills": "python, fastapi",
                       "years_of_experience": 2}, "email": "asha@example.com",
           "cover_letter": "Keen to contribute."}

def test_walk_completes_multistep(load_fixture):
    cfg = dict(PROFILE, fit_gate_enabled=False)  # isolate the walk from the gate
    driver = load_fixture("multistep.html")
    result = sff.walk_multi_step_form(driver, cfg, max_steps=6)
    assert result == "submitted"

def test_fit_gate_skips_unpaid_on_real_dom(load_fixture, chrome_driver):
    # Page whose JD text screams unpaid/scam → should_apply vetoes → 'skipped'.
    html = ("data:text/html,<html><body><h1>Intern</h1><p>" +
            "This is an unpaid internship with no stipend. " * 4 +
            "You must pay a registration fee to apply.</p>"
            "<form><input id='n'><button>Submit application</button></form></body></html>")
    chrome_driver.get(html)
    def _unpaid_llm(prompt, **kw):
        return ('{"keywords":["intern"],"must_haves":[],"nice_to_haves":[],'
                '"seniority":"intern","archetype":"intern","red_flags":["unpaid","registration fee"]}')
    cfg = dict(PROFILE, _jd_llm=_unpaid_llm)
    result = sff.walk_multi_step_form(chrome_driver, cfg, max_steps=3)
    assert result == "skipped"
