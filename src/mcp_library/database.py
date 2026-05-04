"""SQLite database manager for library."""

import os
import sqlite3
import aiosqlite
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List


class LibraryDatabase:
    """Manage SQLite database for book library."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file.
                    If not provided, uses LIBRARY_DB_PATH env var or default.
        """
        if db_path is None:
            db_path = os.getenv(
                "LIBRARY_DB_PATH",
                str(Path.home() / "Books" / ".library.db")
            )

        self.db_path = db_path
        self._ensure_db_directory()

    def _ensure_db_directory(self):
        """Ensure database directory exists."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_schema(self):
        """Create database tables from schema.sql."""
        schema_path = Path(__file__).parent.parent.parent / "schema.sql"

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()

    async def add_book(self, book_data: Dict[str, Any]) -> int:
        """Add a book to the database.

        Args:
            book_data: Dictionary containing book fields

        Returns:
            ID of the newly created book
        """
        fields = ", ".join(book_data.keys())
        placeholders = ", ".join(["?" for _ in book_data])
        values = tuple(book_data.values())

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"INSERT INTO books ({fields}) VALUES ({placeholders})",
                values
            )
            await db.commit()
            return cursor.lastrowid

    async def search_books(
        self,
        query: Optional[str] = None,
        language: Optional[str] = None,
        author: Optional[str] = None,
        file_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Search books with filters.

        Args:
            query: Search in title, author, filename
            language: Filter by language
            author: Filter by author
            file_type: Filter by file type
            limit: Maximum results

        Returns:
            List of matching books
        """
        conditions = []
        params = []

        if query:
            conditions.append(
                "(title LIKE ? OR author LIKE ? OR filename LIKE ?)"
            )
            search_term = f"%{query}%"
            params.extend([search_term, search_term, search_term])

        if language:
            conditions.append("language = ?")
            params.append(language)

        if author:
            conditions.append("author LIKE ?")
            params.append(f"%{author}%")

        if file_type:
            conditions.append("file_type = ?")
            params.append(file_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        params.append(offset)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM books
                WHERE {where_clause}
                ORDER BY title
                LIMIT ? OFFSET ?
                """,
                params
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_book_by_id(self, book_id: int) -> Optional[Dict[str, Any]]:
        """Get book by ID.

        Args:
            book_id: Book ID

        Returns:
            Book data or None if not found
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM books WHERE id = ?",
                (book_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_book(self, book_id: int, updates: Dict[str, Any]):
        """Update book fields.

        Args:
            book_id: Book ID
            updates: Dictionary of fields to update
        """
        print(f"DEBUG: opening db at {self.db_path}", file=sys.stderr)
        print(f"DEBUG: updates={updates}", file=sys.stderr)
        try:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [book_id]
            async with aiosqlite.connect(self.db_path) as db:
                print(f"DEBUG: connected, executing update", file=sys.stderr)
                await db.execute(
                    f"UPDATE books SET {set_clause} WHERE id = ?",
                    values
                )
                await db.commit()
                print(f"DEBUG: committed OK", file=sys.stderr)
        except Exception as e:
            print(f"DEBUG: exception {type(e).__name__}: {e}", file=sys.stderr)
            raise

    async def get_books_by_language(self, language: str) -> List[Dict[str, Any]]:
        """Get all books in a specific language.

        Args:
            language: Language code (en, ru, de, cs)

        Returns:
            List of books
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM books WHERE language = ? ORDER BY title",
                (language,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_books_with_isbn(self) -> List[Dict[str, Any]]:
        """Get all books that have an ISBN."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, isbn, title, author, filename FROM books WHERE isbn IS NOT NULL"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_books_for_enrichment(
        self,
        file_type: str,
        limit: int,
        offset: int,
    ) -> List[Dict[str, Any]]:
        """Get books with title+author but missing enrichment metadata."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM books
                   WHERE file_type = ?
                   AND title IS NOT NULL
                   AND author IS NOT NULL
                   AND title NOT LIKE '%.qxd%'
                   AND title NOT LIKE '%.doc%'
                   AND title NOT LIKE '%.qxp%'
                   AND title NOT LIKE 'Microsoft Word%'
                   AND NOT (
                       publisher IS NOT NULL
                       AND year IS NOT NULL
                       AND isbn IS NOT NULL
                   )
                   ORDER BY title
                   LIMIT ? OFFSET ?""",
                (file_type, limit, offset)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

def init_database_cli():
    """CLI command to initialize database."""
    import asyncio

    db_path = os.getenv("LIBRARY_DB_PATH")
    db = LibraryDatabase(db_path)

    async def init():
        await db.initialize_schema()
        print(f"✅ Database initialized at: {db.db_path}")

    asyncio.run(init())


if __name__ == "__main__":
    init_database_cli()
