"""Origin check before opening a URL from a saved browser chat."""
from urllib.parse import urlsplit


def matches_saved_origin(site, url):
    page = urlsplit(url)
    return bool(site and page.scheme == 'https' and page.netloc == urlsplit(site['new_chat_url']).netloc)
