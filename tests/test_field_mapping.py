"""
TDD tests for field mapping and hallucination prevention.
"""

import sys
import os

# Ensure the root folder is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents")))

import google_form_filler
import smart_form_filler

def test_google_form_filler_name_hallucination():
    config = {
        "email": "candidate@example.com",
        "profile": {
            "full_name": "John Doe",
            "college": "State University",
            "current_company": "Acme Corp",
            "current_role": "Software Engineer"
        }
    }

    # "college name" should map to college, not full name
    assert google_form_filler.match_answer("college name", config) == "State University"
    assert google_form_filler.match_answer("university name", config) == "State University"

    # "company name" should map to current company, not full name
    assert google_form_filler.match_answer("company name", config) == "Acme Corp"
    assert google_form_filler.match_answer("employer name", config) == "Acme Corp"

    # "your name" should map to full name
    assert google_form_filler.match_answer("your name", config) == "John Doe"
    assert google_form_filler.match_answer("full name", config) == "John Doe"


def test_smart_form_filler_name_hallucination():
    config = {
        "email": "candidate@example.com",
        "profile": {
            "full_name": "John Doe",
            "college": "State University",
            "current_company": "Acme Corp",
            "current_role": "Software Engineer"
        }
    }

    # Let's inspect rules built by smart_form_filler
    rules = smart_form_filler._build_field_rules(config)

    # Let's test how a label matches the rules
    def find_match(label, rules):
        c = label.lower()
        for keywords, value in rules:
            if value:
                for kw in keywords:
                    if kw in c:
                        if kw == "name":
                            exclude = ["company", "organization", "college", "university", "degree", "course", "project", 
                                       "father", "mother", "reference", "file", "school", "employer", "manager", "recruiter", 
                                       "friend", "spokesperson", "street", "city", "country", "state", "branch", 
                                       "specialization", "stream", "department", "major", "job", "position", "role", "title",
                                       "spouse", "child", "emergency", "contact", "referee", "professor", "teacher", "ref"]
                            if any(e in c for e in exclude):
                                continue
                        return value
        return None

    # "college name" should match State University, not John Doe
    assert find_match("college name", rules) == "State University"
    # "company name" should match Acme Corp, not John Doe
    assert find_match("company name", rules) == "Acme Corp"
    # "your name" should match John Doe
    assert find_match("your name", rules) == "John Doe"
