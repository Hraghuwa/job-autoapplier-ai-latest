"""Live-DOM test of job_finder.extract_google_links against a Google-results-like
page. Verifies the FIND step: real job links extracted, junk filtered, and
google.com/url?q= redirect-wrapped results unwrapped (not dropped)."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agents")))
import job_finder

def test_extracts_job_links_filters_junk(load_fixture):
    driver = load_fixture("google_results.html")
    urls = [u if isinstance(u, str) else u.get("url") for u in
            job_finder.extract_google_links(driver, [], set())]
    joined = " ".join(urls)
    assert any("greenhouse.io/acme/jobs/123" in u for u in urls)
    assert any("jobs.lever.co/foo" in u for u in urls)
    assert any("internshala.com/internship/detail/xyz" in u for u in urls)
    # junk must be filtered
    assert "youtube.com" not in joined and "wikipedia.org" not in joined
    assert "accounts.google.com" not in joined

def test_unwraps_google_redirect_results(load_fixture):
    driver = load_fixture("google_results.html")
    urls = [u if isinstance(u, str) else u.get("url") for u in
            job_finder.extract_google_links(driver, [], set())]
    # the wrapped greenhouse/beta/jobs/999 result must be recovered, not dropped
    assert any("greenhouse.io/beta/jobs/999" in u for u in urls), \
        f"google-redirect-wrapped job link was dropped: {urls}"
