"""
URL normalization utilities for job deduplication.
"""

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def normalize_url(url: str) -> str:
    """
    Normalizes a URL to a canonical representation to prevent duplicate processing.
    Strips trailing slashes, tracking/referral parameters, and normalizes domain names.
    """
    if not url:
        return ""
    
    url = url.strip()
    url_lower = url.lower()
    if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
        return url_lower
        
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower().replace("www.", "")
        
        # Normalize path: strip trailing slash
        path = parsed.path
        if path == "/":
            path = ""
        elif path.endswith("/") and len(path) > 1:
            path = path[:-1]
            
        # Parse and filter query parameters
        query_params = parse_qsl(parsed.query)
        
        # Tracking/referral/social params to discard
        tracking_keys = {
            "ref", "refid", "ref_id", "refid", "refid", "ref_url",
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
            "trackingid", "trackid", "tracking_id", "track_id", "trkid", "trk",
            "sessionnum", "session_num", "position", "pagenum", "page_num",
            "orgpageelement", "sp_id", "gclid", "fbclid", "affiliate", "source"
        }
        
        filtered_params = []
        for k, v in query_params:
            k_lower = k.lower()
            if k_lower in tracking_keys:
                continue
            if k_lower.startswith("utm_") or k_lower.startswith("ref_") or k_lower.startswith("track_"):
                continue
            filtered_params.append((k_lower, v))
            
        # Sort parameters to ensure consistent query string
        filtered_params.sort()
        
        # Rebuild query string
        query = urlencode(filtered_params) if filtered_params else ""
        
        # Rebuild the final URL without fragment
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))
        return normalized
    except Exception:
        return url.lower()
