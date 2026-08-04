"""Common URL and response-size checks for Cloud-originated downloads."""

from urllib.parse import urljoin, urlparse


MAX_CLOUD_DOWNLOAD_BYTES = 200 * 1024 * 1024


def validate_download_url(raw_url: str, base_url: str, *, allow_signed_url: bool = False) -> str:
    """Return a normalized download URL, rejecting SSRF-prone destinations."""
    value = str(raw_url or "").strip()
    base = urlparse(str(base_url or "").strip())
    if base.scheme not in {"http", "https"} or not base.hostname:
        raise ValueError("Cloud base URL is invalid")
    parsed = urlparse(urljoin(str(base_url).rstrip("/") + "/", value))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("download URL must use HTTP or HTTPS")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("download URL contains forbidden URL components")
    same_origin = parsed.scheme == base.scheme and parsed.hostname.lower() == base.hostname.lower()
    same_origin = same_origin and (parsed.port or _default_port(parsed.scheme)) == (base.port or _default_port(base.scheme))
    signed = "X-Amz-Algorithm" in parsed.query and "X-Amz-Signature" in parsed.query
    if not same_origin and not (allow_signed_url and signed):
        raise ValueError("download URL is outside the configured Cloud origin")
    return parsed.geturl()


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80
