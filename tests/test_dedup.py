"""
Unit and integration tests for URL normalization and job deduplication.
"""

from unittest.mock import MagicMock, patch
from url_utils import normalize_url
import job_finder
import web_search_applier

def test_normalize_url_basic():
    assert normalize_url("https://www.google.com/") == "https://google.com"
    assert normalize_url("HTTPS://WWW.LINKEDIN.COM/jobs/view/123/") == "https://linkedin.com/jobs/view/123"

def test_normalize_url_query_params():
    url_with_tracking = "https://example.com/apply?utm_source=linkedin&utm_campaign=winter&gh_jid=999&ref=referral"
    # should strip utm_source, utm_campaign, and ref, but keep gh_jid
    expected = "https://example.com/apply?gh_jid=999"
    assert normalize_url(url_with_tracking) == expected

def test_normalize_url_sorting():
    url1 = "https://example.com/job?z=1&a=2"
    url2 = "https://example.com/job?a=2&z=1"
    assert normalize_url(url1) == normalize_url(url2)

def test_normalize_url_fragment():
    url = "https://example.com/job#section-apply"
    assert normalize_url(url) == "https://example.com/job"

def test_extract_google_links_dedup():
    driver = MagicMock()
    # Create two links: one is new, one is duplicate (differing only by trailing slash / tracking query params)
    link1 = MagicMock()
    link1.get_attribute.side_effect = lambda attr: "https://example.com/jobs/123?utm_source=feed" if attr == "href" else ""
    
    link2 = MagicMock()
    link2.get_attribute.side_effect = lambda attr: "https://example.com/jobs/456/" if attr == "href" else ""
    
    driver.find_elements.return_value = [link1, link2]
    
    # Applied list contains the normalized version of link1
    applied_urls = {"https://example.com/jobs/123"}
    found_urls = []
    
    results = job_finder.extract_google_links(driver, found_urls, applied_urls)
    
    # link1 should be skipped because its normalized form matches the applied_urls
    # link2 should be returned
    assert len(results) == 1
    assert results[0] == "https://example.com/jobs/456/"

def test_web_search_applier_search_and_apply_dedup():
    driver = MagicMock()
    config = {
        "web_search": {
            "enabled": True,
            "max_queries": 1,
            "tab_limit": 10
        },
        "keywords": ["Software Engineer"]
    }
    
    # Mock extract_google_links to return a duplicate that should be caught by web_search_applier local dedup
    # and a new link.
    mock_links = [
        "https://example.com/jobs/123?utm_medium=email",
        "https://example.com/jobs/789"
    ]
    
    applied_urls = {"https://example.com/jobs/123"}
    
    # Patch helper methods so it doesn't do a real Google search and doesn't apply to jobs
    with patch("job_finder.extract_google_links", return_value=mock_links), \
         patch("web_search_applier.apply_to_job_url", return_value=True), \
         patch("web_search_applier.is_driver_alive", return_value=True), \
         patch("web_search_applier.should_stop", return_value=False), \
         patch("time.sleep"):
        
        count, new_applied = web_search_applier.search_and_apply(driver, config, applied_urls=applied_urls)
        
        # https://example.com/jobs/123?utm_medium=email should be skipped because it normalizes to https://example.com/jobs/123
        # which is in applied_urls.
        # Only https://example.com/jobs/789 should be processed.
        assert len(new_applied) == 1
        assert new_applied[0]["url"] == "https://example.com/jobs/789"
