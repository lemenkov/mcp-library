"""MCP server for library management."""

import os
import argparse
from typing import Optional
from fastmcp import FastMCP
from .database import LibraryDatabase


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


@mcp.tool()
async def search_library(
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


@mcp.tool()
async def get_book_info(book_id: int) -> str:
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


@mcp.tool()
async def list_by_language(language: str) -> str:
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
