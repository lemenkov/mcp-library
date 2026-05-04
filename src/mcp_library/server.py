"""MCP server for library management."""

import os
import argparse
import asyncio
from typing import Optional
from fastmcp import FastMCP
from .database import LibraryDatabase
from .enrichers import lookup_isbn_openlibrary
from .enrichers import lookup_title_author_openlibrary
from .enrichers import lookup_title_author_fantlab
from .enrichers import lookup_title_author_gutenberg
from .enrichers import lookup_title_author_google_books

# Initialize FastMCP server
mcp = FastMCP("Library MCP Server")

# Global database instance
db: Optional[LibraryDatabase] = None


def get_db() -> LibraryDatabase:
    """Get or create the database instance."""
    global db
    if db is None:
        db = LibraryDatabase()
    return db


@mcp.tool(
    tags={"read"},
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def search(
    query: Optional[str] = None,
    language: Optional[str] = None,
    author: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Search books in your library.

    Args:
        query: Search in title, author, filename
        language: Filter by language (en, ru, de, cs)
        author: Filter by author name
        file_type: Filter by file type (pdf, djvu, epub, fb2, doc)
        limit: Maximum results (default: 20)

    Returns:
        Formatted list of matching books
    """
    database = get_db()
    books = await database.search_books(query, language, author, file_type, limit)

    if not books:
        return "No books found matching your criteria."

    response = f"Found {len(books)} book(s):\n\n"

    for book in books:
        response += f"**{book.get('title') or book['filename']}**\n"
        if book.get('author'):
            response += f"  Author: {book['author']}\n"
        if book.get('year'):
            response += f"  Year: {book['year']}\n"
        if book.get('language'):
            response += f"  Language: {book['language']}\n"
        response += f"  Format: {book['file_type']}\n"
        response += f"  ID: {book['id']}\n"
        response += "\n"

    return response


@mcp.tool(
    tags={"read"},
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_book(book_id: int) -> str:
    """Get detailed information about a specific book.

    Args:
        book_id: Book database ID

    Returns:
        Detailed book information
    """
    database = get_db()
    book = await database.get_book_by_id(book_id)

    if not book:
        return f"Book with ID {book_id} not found."

    response = f"**{book.get('title') or book['filename']}**\n\n"

    if book.get('author'):
        response += f"Author: {book['author']}\n"
    if book.get('publisher'):
        response += f"Publisher: {book['publisher']}\n"
    if book.get('year'):
        response += f"Year: {book['year']}\n"
    if book.get('isbn'):
        response += f"ISBN: {book['isbn']}\n"
    if book.get('language'):
        response += f"Language: {book['language']}\n"

    response += f"\nFile: {book['filename']}\n"
    response += f"Type: {book['file_type']}\n"
    response += f"URI: {book['uri']}\n"

    if book.get('file_size'):
        size_mb = book['file_size'] / (1024 * 1024)
        response += f"Size: {size_mb:.2f} MB\n"

    if book.get('page_count'):
        response += f"Pages: {book['page_count']}\n"

    if book.get('content_type'):
        response += f"\nContent Type: {book['content_type']}\n"

    if book.get('ocr_quality'):
        response += f"OCR Quality: {book['ocr_quality']}\n"

    if book.get('notes'):
        response += f"\nNotes: {book['notes']}\n"

    return response


@mcp.tool(
    tags={"read"},
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def list_books(language: str) -> str:
    """List all books in a specific language.

    Args:
        language: Language code (en, ru, de, cs)

    Returns:
        List of books in that language
    """
    database = get_db()
    books = await database.get_books_by_language(language)

    if not books:
        return f"No books found in language: {language}"

    response = f"Found {len(books)} book(s) in {language.upper()}:\n\n"

    for book in books:
        response += f"- {book.get('title') or book['filename']}"
        if book.get('author'):
            response += f" by {book['author']}"
        if book.get('year'):
            response += f" ({book['year']})"
        response += f" [ID: {book['id']}]\n"

    return response


@mcp.tool(
    tags={"write"},
    annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
)
async def enrich_by_isbn(dry_run: bool = False) -> str:
    """Enrich book metadata by querying Open Library for books with ISBNs.

    Args:
        dry_run: If True, show what would be updated without writing to DB

    Returns:
        Summary of enrichment results
    """
    database = get_db()
    books = await database.get_books_with_isbn()

    if not books:
        return "No books with ISBNs found in the database."

    results = []
    updated = 0
    not_found = 0
    errors = 0

    for book in books:
        isbn = book["isbn"]
        book_id = book["id"]
        label = book.get("title") or book["filename"]

        metadata = lookup_isbn_openlibrary(isbn)

        if metadata is None:
            not_found += 1
            results.append(f"❌ [{isbn}] {label} — not found in Open Library")
            continue

        # Remove internal keys before DB update
        subjects = metadata.pop("_subjects", [])
        raw = metadata.get("raw_metadata")

        if dry_run:
            results.append(
                f"🔍 [{isbn}] {label}\n"
                f"   Would update: {', '.join(k for k in metadata if k != 'raw_metadata')}"
            )
        else:
            try:
                await database.update_book(book_id, metadata)
                updated += 1
                results.append(
                    f"✅ [{isbn}] {label}\n"
                    f"   Updated: {', '.join(k for k in metadata if k != 'raw_metadata')}"
                )
            except Exception as e:
                errors += 1
                results.append(f"⚠️ [{isbn}] {label} — DB error: {e}")

    summary = f"ISBN enrichment complete: {updated} updated, {not_found} not found, {errors} errors\n\n"
    return summary + "\n".join(results)


@mcp.tool(
    tags={"write"},
    annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
)
async def enrich_by_title_author(
    file_type: str = "fb2",
    limit: int = 50,
    offset: int = 0,
    dry_run: bool = True,
    min_similarity: float = 0.7,
) -> str:
    """Enrich book metadata by searching Open Library with title + author.

    Args:
        file_type: File type to process (default: fb2)
        limit: Max books to process in one run (default: 50)
        dry_run: If True, show what would be updated without writing to DB
        min_similarity: Minimum title match confidence 0-1 (default: 0.7)

    Returns:
        Summary of enrichment results
    """
    database = get_db()
    candidates = await database.get_books_for_enrichment(file_type, limit, offset)

    if not candidates:
        return f"No {file_type} books with title+author found."

    updated = 0
    not_found = 0
    low_confidence = 0
    errors = 0
    results = []

    for book in candidates:
        book_id = book["id"]
        title = book["title"]
        author = book["author"]

        updates = {}
        similarity = 0

        for lookup_fn in [
            lookup_title_author_openlibrary,
            lookup_title_author_fantlab,
            lookup_title_author_google_books,
        ]:
            result = lookup_fn(title, author, min_similarity=min_similarity)
            if result is None:
                continue

            sim = result.pop("_similarity", 0)
            result.pop("_subjects", None)
            isbn_found = result.pop("_isbn", None)

            if isbn_found and not book.get("isbn") and "isbn" not in updates:
                updates["isbn"] = isbn_found

            if sim > similarity:
                similarity = sim

            # Only take fields we don't have yet
            for k, v in result.items():
                if not book.get(k) and k not in updates:
                    updates[k] = v

            # Stop early if we have all key fields
            if all(
                updates.get(f) or book.get(f)
                for f in ("title", "author", "publisher", "year")
            ):
                break

        # Slow down to avoid hitting API rate limits
        await asyncio.sleep(0.3)

        if not updates:
            not_found += 1
            results.append(f"❌ Not found: {title} / {author}")
            continue

        if dry_run:
            results.append(
                f"🔍 [{similarity:.0%}] {title}\n"
                f"   Would update: {', '.join(updates.keys())}"
            )
        else:
            try:
                await database.update_book(book_id, updates)
                updated += 1
                results.append(
                    f"✅ [{similarity:.0%}] {title}\n"
                    f"   Updated: {', '.join(updates.keys())}"
                )
            except Exception as e:
                errors += 1
                results.append(f"⚠️  DB error for {title}: {e}")

    summary = (
        f"Title+author enrichment ({'dry run' if dry_run else 'live'}) — "
        f"{file_type.upper()}, {len(candidates)} candidates:\n"
        f"{updated} updated, {not_found} not found, "
        f"{low_confidence} low confidence, {errors} errors\n\n"
    )
    return summary + "\n".join(results)

@mcp.tool(
    tags={"write"},
    annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
)
async def enrich_by_gutenberg(
    file_type: str = "pdf",
    limit: int = 50,
    offset: int = 0,
    dry_run: bool = True,
    min_similarity: float = 0.6,
) -> str:
    """Enrich book metadata by searching Project Gutenberg (public domain classics).

    Best for pre-1928 works: Verne, Dumas, Conan Doyle, Cooper, Dickens, etc.
    Queries gutendex.com — no API key needed.

    Args:
        file_type: File type to process (default: pdf)
        limit: Max books to process in one run (default: 50)
        offset: Skip first N candidates (default: 0)
        dry_run: If True, show what would be updated without writing to DB
        min_similarity: Minimum title match confidence 0-1 (default: 0.6)

    Returns:
        Summary of enrichment results
    """
    from .enrichers import lookup_title_author_gutenberg

    database = get_db()
    candidates = await database.get_books_for_enrichment(file_type, limit, offset)

    if not candidates:
        return f"No {file_type} books with title+author found needing enrichment."

    candidates = [b for b in candidates
              if b.get("language") in ("en", None)
              and not any(ord(c) > 127 for c in (b.get("title") or "")[:20])]

    updated = 0
    not_found = 0
    errors = 0
    results = []

    for book in candidates:
        book_id = book["id"]
        title = book["title"]
        author = book["author"]

        metadata = lookup_title_author_gutenberg(
            title, author, min_similarity=min_similarity
        )

        if metadata is None:
            not_found += 1
            continue  # silent skip — most books won't be on Gutenberg

        similarity = metadata.pop("_similarity", 0)
        subjects = metadata.pop("_subjects", [])

        # Don't overwrite existing fields
        updates = {k: v for k, v in metadata.items() if not book.get(k)}

        if not updates:
            results.append(f"⏭️  No new fields: {title}")
            continue

        if dry_run:
            results.append(
                f"🔍 [{similarity:.0%}] {title}\n"
                f"   Would update: {', '.join(updates.keys())}"
            )
        else:
            try:
                await database.update_book(book_id, updates)
                updated += 1
                results.append(
                    f"✅ [{similarity:.0%}] {title}\n"
                    f"   Updated: {', '.join(updates.keys())}"
                )
            except Exception as e:
                errors += 1
                results.append(f"⚠️  DB error for {title}: {e}")

        await asyncio.sleep(0.2)

    summary = (
        f"Gutenberg enrichment ({'dry run' if dry_run else 'live'}) — "
        f"{file_type.upper()}, {len(candidates)} candidates:\n"
        f"{updated} updated, {not_found} not found on Gutenberg, {errors} errors\n\n"
    )
    return summary + "\n".join(results) if results else summary

@mcp.tool(
    tags={"read"},
    annotations={"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
)
async def check_health() -> str:
    """Test if DB is writable."""
    import aiosqlite
    import os
    from pathlib import Path
    db_path = os.getenv("LIBRARY_DB_PATH", str(Path.home() / "Books" / ".library.db"))
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("UPDATE books SET notes='test' WHERE id=1")
            await db.commit()
            return f"Write OK to {db_path}"
    except Exception as e:
        return f"FAILED on {db_path}: {type(e).__name__}: {e}\nUID={os.getuid()} GID={os.getgid()}"

def main():
    """Main entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="Library MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to in HTTP mode (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to in HTTP mode (default: 8080)"
    )

    args = parser.parse_args()

    # Verify database path
    db_path = os.getenv("LIBRARY_DB_PATH")
    books_dir = os.getenv("LIBRARY_BOOKS_DIR")

    if not books_dir:
        print("Warning: LIBRARY_BOOKS_DIR not set. Set it with:")
        print("  export LIBRARY_BOOKS_DIR='/home/Username/Books'")

    if not db_path:
        print("Info: Using default database location")

    # Run the server
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport="http", host=args.host, port=args.port, path="/mcp")


if __name__ == "__main__":
    main()
