"""Helpers for the WHOI HF radar image page."""

from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx2

# The folder of images the page shows. This is a stand-in for development: it
# is NOAA's GOES-19 northeast satellite imagery, which happens to be published
# the same way we expect WHOI's radar images to be -- a folder index of dated
# image files. Swap it for the real WHOI folder (issue #173).
LISTING_URL = "https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/ne/GEOCOLOR/"

# File types a browser can show in an image tag.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")

# How many images the carousel shows: two weeks of daily images, enough to see
# recent gaps without making the row of thumbnails unreadable.
DEFAULT_LIMIT = 14

# Seconds to wait on the image listing. Without a limit, a server that accepts
# the connection and then goes quiet leaves the page loading forever.
HTTP_TIMEOUT = 30


def filename(url: str) -> str:
    """The file name at the end of an image URL, to label the image with."""
    # Drop anything after the file name: "?v=2" (a cache buster) or "#top".
    path = url.split("?", 1)[0].split("#", 1)[0]
    # Take the part after the last "/", ignoring a trailing one so that
    # ".../images/" gives "images" rather than "". A URL with no "/" left to
    # split on, or nothing after it, is used as the label as-is.
    return path.rstrip("/").rsplit("/", 1)[-1] or url


def is_image_url(url: str) -> bool:
    """Whether a URL looks like an image we can show."""
    # Checked against the file name rather than the whole URL, so that a
    # ".png?v=2" still counts.
    return filename(url).lower().endswith(IMAGE_SUFFIXES)


class _LinkFinder(HTMLParser):
    """Collects the target of every link on a page."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs += [value for name, value in attrs if name == "href" and value]


def image_urls(listing_html: str, listing_url: str) -> list[str]:
    """The image URLs linked from a page listing a folder of images."""
    finder = _LinkFinder()
    finder.feed(listing_html)
    # A link's target may be a bare file name, a path, or a full URL. Joining
    # each one to the address of the listing page fills in whatever is missing
    # and leaves an already-complete URL alone.
    return [urljoin(listing_url, href) for href in finder.hrefs if is_image_url(href)]


def fetch_listing(listing_url: str) -> str:
    """Download the page that lists the images."""
    response = httpx2.get(listing_url, timeout=HTTP_TIMEOUT)
    # Turns a "404 Not Found" or "500" answer into an error, rather than
    # handing back the error page's own HTML as though it were a listing.
    response.raise_for_status()
    return response.text


def latest_images(listing_url: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    """The newest images in the listed folder, most recent first."""
    urls = image_urls(fetch_listing(listing_url), listing_url)
    # The file names start with the date the image covers, so putting them in
    # reverse alphabetical order is the same as putting them newest first.
    urls.sort(key=filename, reverse=True)
    return urls[:limit]
