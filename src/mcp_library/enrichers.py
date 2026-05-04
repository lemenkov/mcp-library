"""External metadata enrichment from public APIs."""

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

OPENLIBRARY_API = "https://openlibrary.org/api/books"
OPENLIBRARY_SEARCH = "https://openlibrary.org/search.json"
FANTLAB_API = "https://api.fantlab.ru"
GUTENDEX_API = "https://gutendex.com/books"
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

# Valid ISBN after normalization
_ISBN_RE = re.compile(r'^\d{9}[\dX]$|^\d{13}$')

def _similarity(a: str, b: str) -> float:
    """Simple string similarity ratio between 0 and 1."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def _normalize_isbn(isbn: str) -> Optional[str]:
    """Normalize ISBN to digits-only (plus trailing X for ISBN-10).

    Returns:
        Normalized ISBN string, or None if it cannot be normalized.
    """
    # Strip known prefixes case-insensitively
    cleaned = re.sub(
        r'^(urn:isbn:|isbn:?\s*)',
        '',
        isbn.strip(),
        flags=re.IGNORECASE
    )

    # Replace Cyrillic Х/х with Latin X/x (common OCR mistake)
    cleaned = cleaned.replace('\u0425', 'X').replace('\u0445', 'x')

    # Strip hyphens and spaces
    cleaned = cleaned.replace('-', '').replace(' ', '').upper()

    if _ISBN_RE.match(cleaned):
        return cleaned

    logger.warning("Could not normalize ISBN %r → %r", isbn, cleaned)
    return None

def _clean_author_for_search(author: str) -> str:
    """Strip birth/death years and verbose qualifiers from author names."""
    # Remove date ranges like (1853-1942) or , 1784-1853
    author = re.sub(r'[,(]\s*\d{4}\s*[-–]\s*\d{4}\s*[)]?', '', author)
    # Remove honorifics like Sir, Dr, etc.
    author = re.sub(r'\b(Sir|Dr|Prof|Lord|Lady)\b', '', author, flags=re.IGNORECASE)
    # Remove parenthetical full names like (William Matthew Flinders)
    author = re.sub(r'\([^)]+\)', '', author)
    return author.strip(' ,')

def lookup_isbn_openlibrary(isbn: str) -> Optional[Dict[str, Any]]:
    """Query Open Library for metadata by ISBN.

    Args:
        isbn: ISBN-10 or ISBN-13 string (hyphens are stripped automatically)

    Returns:
        Normalized metadata dict or None if not found
    """
    isbn_clean = _normalize_isbn(isbn)
    if isbn_clean is None:
        return None

    url = (
        f"{OPENLIBRARY_API}"
        f"?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
    )

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "mcp-library/0.1 (https://github.com/lemenkov/mcp-library)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    key = f"ISBN:{isbn_clean}"
    if key not in data:
        return None

    book = data[key]

    result: Dict[str, Any] = {}

    if book.get("title"):
        result["title"] = book["title"]

    # Authors: list of {"name": "..."} dicts
    authors = book.get("authors", [])
    if authors:
        result["author"] = "; ".join(a.get("name", "") for a in authors if a.get("name"))

    # Publishers: list of {"name": "..."} dicts
    publishers = book.get("publishers", [])
    if publishers:
        result["publisher"] = publishers[0].get("name")

    # Publish date: often "2003" or "January 1, 2003"
    publish_date = book.get("publish_date", "")
    if publish_date:
        year_match = re.search(r'\b(1[5-9]\d{2}|20\d{2})\b', publish_date)
        if year_match:
            result["year"] = int(year_match.group(1))

    # Number of pages
    if book.get("number_of_pages"):
        result["page_count"] = book["number_of_pages"]

    # Subjects: list of {"name": "..."} dicts — store as notes for now
    subjects = book.get("subjects", [])
    if subjects:
        result["_subjects"] = [s.get("name", "") for s in subjects[:10] if s.get("name")]

    return result

def lookup_title_author_openlibrary(
    title: str,
    author: str,
    min_similarity: float = 0.7,
) -> Optional[Dict[str, Any]]:
    """Query Open Library by title and author.

    Args:
        title: Book title
        author: Author name
        min_similarity: Minimum title similarity to accept a match (0-1)

    Returns:
        Normalized metadata dict, or None if no confident match found
    """

    params = urllib.parse.urlencode({
        "title": title,
        "author": author,
        "limit": 1,
        "fields": "title,author_name,publisher,first_publish_year,number_of_pages_median,isbn",
    })
    url = f"{OPENLIBRARY_SEARCH}?{params}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "mcp-library/0.1 (https://github.com/lemenkov/mcp-library)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    docs = data.get("docs", [])
    if not docs:
        return None

    doc = docs[0]

    # Verify title similarity to avoid false matches
    returned_title = doc.get("title", "")
    similarity = _similarity(title, returned_title)
    if similarity < min_similarity:
        return None

    result: Dict[str, Any] = {"_similarity": similarity}

    if returned_title:
        result["title"] = returned_title

    authors = doc.get("author_name", [])
    if authors:
        result["author"] = "; ".join(authors)

    publishers = doc.get("publisher", [])
    if publishers:
        result["publisher"] = publishers[0]

    if doc.get("first_publish_year"):
        result["year"] = doc["first_publish_year"]

    if doc.get("number_of_pages_median"):
        result["page_count"] = doc["number_of_pages_median"]

    # Grab first ISBN if we don't have one
    isbns = doc.get("isbn", [])
    if isbns:
        result["_isbn"] = isbns[0]

    return result

def lookup_title_author_fantlab(
    title: str,
    author: str,
    min_similarity: float = 0.6,
) -> Optional[Dict[str, Any]]:
    """Query Fantlab.ru for metadata by title and author.

    Best for Russian/Soviet SF/F and translated works in Russian.

    Args:
        title: Book title (Cyrillic preferred)
        author: Author name (Cyrillic preferred)
        min_similarity: Minimum title similarity to accept (default: 0.6,
                        lower than Open Library since Russian titles vary more)

    Returns:
        Normalized metadata dict, or None if no confident match found
    """

    query = f"{title} {author}"
    url = f"{FANTLAB_API}/search-editions?q={urllib.parse.quote(query)}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "mcp-library/0.1 (https://github.com/lemenkov/mcp-library)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    matches = data.get("matches", [])
    if not matches:
        return None

    # Take the highest-weight match
    best = matches[0]

    returned_title = best.get("name", "")
    similarity = _similarity(title, returned_title)
    if similarity < min_similarity:
        return None

    result: Dict[str, Any] = {"_similarity": similarity}

    if returned_title:
        result["title"] = returned_title

    if best.get("autors"):
        result["author"] = best["autors"]

    if best.get("publisher"):
        result["publisher"] = best["publisher"]

    if best.get("year"):
        result["year"] = int(best["year"])

    # Grab ISBN if present (may be comma-separated for multi-volume editions)
    isbn_raw = best.get("isbn", "")
    if isbn_raw:
        # Take the first ISBN only
        first_isbn = isbn_raw.split(",")[0].strip()
        normalized = _normalize_isbn(first_isbn)
        if normalized:
            result["_isbn"] = normalized

    return result

def lookup_title_author_gutenberg(
    title: str,
    author: str,
    min_similarity: float = 0.6,
) -> Optional[Dict[str, Any]]:
    """Query Project Gutenberg via Gutendex for public domain books.

    Best for pre-1928 classics — Verne, Dumas, Conan Doyle, Cooper, etc.

    Args:
        title: Book title
        author: Author name
        min_similarity: Minimum title similarity to accept (default: 0.6)

    Returns:
        Normalized metadata dict, or None if no confident match found
    """

    logger.warning(f"Gutenberg: checking '{title}' by '{author} ({_clean_author_for_search(author)})'")
    query = f"{title} {_clean_author_for_search(author)}"
    url = f"{GUTENDEX_API}?search={urllib.parse.quote(query)}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "mcp-library/0.1 (https://github.com/lemenkov/mcp-library)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    results = data.get("results", [])
    if not results:
        return None

    best = results[0]

    returned_title = best.get("title", "")
    similarity = _similarity(title, returned_title)
    if similarity < min_similarity:
        return None

    result: Dict[str, Any] = {"_similarity": similarity}

    if returned_title:
        result["title"] = returned_title

    # Authors: list of {"name": "Lastname, Firstname", ...}
    authors = best.get("authors", [])
    if authors:
        result["author"] = "; ".join(a.get("name", "") for a in authors if a.get("name"))

    # Language
    languages = best.get("languages", [])
    if languages:
        result["language"] = languages[0]

    # Subjects as a bonus — store first few
    subjects = best.get("subjects", [])
    if subjects:
        result["_subjects"] = subjects[:5]

    # Gutenberg ID — could store as source_url
    gutenberg_id = best.get("id")
    if gutenberg_id:
        result["source_url"] = f"https://www.gutenberg.org/ebooks/{gutenberg_id}"

    return result


def lookup_title_author_google_books(
    title: str,
    author: str,
    min_similarity: float = 0.8,
) -> Optional[Dict[str, Any]]:
    """Query Google Books API for metadata by title and author.

    Good coverage of academic, niche, and non-English books.
    No API key needed for basic metadata search.

    Args:
        title: Book title
        author: Author name
        min_similarity: Minimum title similarity to accept (default: 0.8)

    Returns:
        Normalized metadata dict, or None if no confident match found
    """

    api_key = os.getenv("GOOGLE_BOOKS_API_KEY", "")
    key_param = f"&key={api_key}" if api_key else ""

    query = f"intitle:{urllib.parse.quote(title)}+inauthor:{urllib.parse.quote(author)}"
    url = f"{GOOGLE_BOOKS_API}?q={query}&maxResults=1&fields=items(volumeInfo){key_param}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "mcp-library/0.1 (https://github.com/lemenkov/mcp-library)"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    items = data.get("items", [])
    if not items:
        return None

    info = items[0].get("volumeInfo", {})

    returned_title = info.get("title", "")
    similarity = _similarity(title, returned_title)
    if similarity < min_similarity:
        return None

    result: Dict[str, Any] = {"_similarity": similarity}

    if returned_title:
        result["title"] = returned_title

    authors = info.get("authors", [])
    if authors:
        result["author"] = "; ".join(authors)

    if info.get("publisher"):
        result["publisher"] = info["publisher"]

    if info.get("publishedDate"):
        year_match = re.search(r'\b(1[5-9]\d{2}|20\d{2})\b', info["publishedDate"])
        if year_match:
            result["year"] = int(year_match.group(1))

    if info.get("pageCount"):
        result["page_count"] = info["pageCount"]

    # Grab ISBN-13 if available
    for identifier in info.get("industryIdentifiers", []):
        if identifier.get("type") == "ISBN_13":
            result["_isbn"] = identifier.get("identifier")
            break

    if info.get("language"):
        result["language"] = info["language"]

    return result
