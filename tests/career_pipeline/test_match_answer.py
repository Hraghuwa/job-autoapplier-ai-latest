"""Pure tests for google_form_filler.match_answer (generic web-form field map).

Catches substring collisions that put the wrong profile value in a field —
e.g. 'Company Name' getting the CANDIDATE's name, or 'Where did you hear about
us?' getting their city.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
from google_form_filler import match_answer

CFG = {"profile": {"full_name": "Asha Rao", "location": "Bengaluru",
                   "current_company": "Acme", "skills": "python"},
       "email": "asha@example.com"}

def test_full_name_maps_to_candidate_name():
    assert match_answer("Full Name", CFG) == "Asha Rao"

def test_company_name_not_candidate_name():
    # The bug: 'name' matched inside 'company name' → returned the candidate.
    assert match_answer("Company Name", CFG) != "Asha Rao"

def test_where_did_you_hear_not_city():
    assert match_answer("Where did you hear about us?", CFG) != "Bengaluru"

def test_current_city_still_maps_to_location():
    assert match_answer("Current City", CFG) == "Bengaluru"

def test_email_and_linkedin_unaffected():
    assert match_answer("Email Address", CFG) == "asha@example.com"

def test_unknown_field_returns_none():
    assert match_answer("Favourite colour", CFG) is None
