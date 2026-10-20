import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "agents"))
from jobspy_fetch import to_postings  # noqa: E402

NAN = float("nan")


def test_prefers_direct_url_and_drops_urlless_rows():
    rows = [
        {"job_url": "https://in.indeed.com/viewjob?jk=1", "job_url_direct": "https://acme.greenhouse.io/j/1",
         "title": "Ops Associate", "location": "Bengaluru", "company": "Acme", "description": NAN},
        {"job_url": "https://www.naukri.com/job/2", "job_url_direct": NAN, "title": "Analyst",
         "location": NAN, "company": "B", "description": "x" * 9000},
        {"job_url": NAN, "job_url_direct": None, "title": "No URL"},
    ]
    out = to_postings(rows)
    assert [p["url"] for p in out] == ["https://acme.greenhouse.io/j/1", "https://www.naukri.com/job/2"]
    assert out[0]["jd"] == "" and out[1]["location"] == "" and len(out[1]["jd"]) == 8000
