"""Run JobSpy and print postings as JSON. Needs Python >= 3.10 + `pip install python-jobspy`.

The agent itself runs on Python 3.9, so job_finder.fetch_jobspy_jobs calls this
script in a separate interpreter. stdin: {"keywords", "locations", "sites", "per_search"}.
stdout: [{url, title, location, company, jd}] in job_finder._board_postings shape.
"""
import json
import sys


def _s(v):
    # pandas NaN / None → ""
    return "" if v is None or v != v else str(v)


def to_postings(rows):
    out = []
    for r in rows:
        # Company ATS page beats the LinkedIn/Indeed listing: no login wall, ContextFill can fill it.
        url = _s(r.get("job_url_direct")) or _s(r.get("job_url"))
        if url:
            out.append({"url": url, "title": _s(r.get("title")), "location": _s(r.get("location")),
                        "company": _s(r.get("company")), "jd": _s(r.get("description"))[:8000]})
    return out


def main():
    from jobspy import scrape_jobs
    args = json.load(sys.stdin)
    loc = (args.get("locations") or ["India"])[0]
    rows = []
    for kw in (args.get("keywords") or [])[:5]:
        try:
            df = scrape_jobs(site_name=args.get("sites"), search_term=kw, google_search_term=f"{kw} jobs in {loc}",
                             location=loc, results_wanted=args.get("per_search", 25), hours_old=72,
                             country_indeed="india", description_format="markdown")
            rows += df.to_dict("records")
        except Exception as e:  # one site/keyword failing must not lose the rest
            print(f"jobspy {kw!r}: {e}", file=sys.stderr)
    json.dump(to_postings(rows), sys.stdout)


if __name__ == "__main__":
    main()
