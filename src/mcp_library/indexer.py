"""Directory indexer for library."""

import os
import asyncio
from pathlib import Path
from typing import Optional
from .database import LibraryDatabase
from .metadata_extractors import MetadataExtractor, METADATA_VERSION


class LibraryIndexer:
    """Index books directory and populate database."""

    def __init__(self, db: LibraryDatabase, books_dir: str):
        """Initialize indexer.

        Args:
            db: Database instance
            books_dir: Path to books directory
        """
        self.db = db
        self.books_dir = Path(books_dir)
        self.extractor = MetadataExtractor()

    async def index_directory(self, force_reindex: bool = False):
        """Scan directory and index all books.

        Args:
            force_reindex: If True, re-index all files even if already indexed
        """
        if not self.books_dir.exists():
            print(f"Error: Books directory not found: {self.books_dir}")
            return

        print(f"Indexing directory: {self.books_dir}")
        print(f"Metadata extraction version: {METADATA_VERSION}")

        # Supported file types
        extensions = {'.pdf', '.djvu', '.epub', '.fb2', '.zip', '.doc', '.docx'}

        files_found = 0
        files_indexed = 0
        files_updated = 0
        files_skipped = 0

        # Walk through directory
        for filepath in self.books_dir.rglob('*'):
            if not filepath.is_file():
                continue

            if filepath.suffix.lower() not in extensions:
                continue

            files_found += 1

            try:
                # Extract metadata
                metadata = self.extractor.extract_all_metadata(str(filepath))

                # Check if file already indexed by hash
                existing_books = await self.db.search_books(
                    query=None,
                    file_type=None,
                    limit=10000  # Increase limit for large collections
                )

                existing_by_hash = [
                    b for b in existing_books
                    if b.get('file_hash') == metadata.get('file_hash')
                ]

                if existing_by_hash:
                    book_id = existing_by_hash[0]['id']
                    existing_version = existing_by_hash[0].get('metadata_version', '0.0.0')

                    # Re-extract if version outdated or force flag
                    if existing_version < METADATA_VERSION or force_reindex:
                        await self.db.update_book(book_id, metadata)
                        files_updated += 1
                    else:
                        files_skipped += 1

                    if files_found % 10 == 0:
                        print(f"Processed {files_found} files... "
                              f"(indexed: {files_indexed}, updated: {files_updated}, "
                              f"skipped: {files_skipped})")
                    continue

                # Add new entry
                await self.db.add_book(metadata)
                files_indexed += 1

                if files_found % 10 == 0:
                    print(f"Processed {files_found} files... "
                          f"(indexed: {files_indexed}, updated: {files_updated}, "
                          f"skipped: {files_skipped})")

            except Exception as e:
                print(f"Error processing {filepath.name}: {e}")
                continue

        print(f"\nIndexing complete!")
        print(f"Total files found: {files_found}")
        print(f"New files indexed: {files_indexed}")
        print(f"Files updated: {files_updated}")
        print(f"Files skipped: {files_skipped}")


def index_cli():
    """CLI command to index books directory."""
    db_path = os.getenv("LIBRARY_DB_PATH")
    books_dir = os.getenv("LIBRARY_BOOKS_DIR")

    if not books_dir:
        print("Error: LIBRARY_BOOKS_DIR environment variable not set")
        print("Set it with: export LIBRARY_BOOKS_DIR='/home/peter/Books'")
        return

    db = LibraryDatabase(db_path)
    indexer = LibraryIndexer(db, books_dir)

    asyncio.run(indexer.index_directory())


if __name__ == "__main__":
    index_cli()
