# mcp-library

MCP server for managing books.

## Overview

This MCP server provides tools for managing an unorganized book collection with:
- Multiple formats: PDF, DjVu, EPUB, FB2, DOC, HTML, JPEG collections
- Multiple languages: Russian, English, German, Czech, etc.
- SQLite database with comprehensive metadata tracking
- Support for partial scans, damaged books, and OCR tracking
- Wikipedia citation generation (Template:Cite_book)
- External metadata integration (WorldCat, OCLC, VIAF, Library of Congress)
- Future OPDS and OCR system integration

## Features

- **Metadata extraction** from PDF, DjVu, EPUB, FB2, DOC files
- **Language detection** from filenames and content
- **ISBN tracking** and bibliographic metadata
- **Quality tracking** for OCR, missing pages, scan quality
- **Version tracking** via SHA256 file hashing
- **URI support** for file://, https://, nfs://, ssh:// locations
- **Wikipedia integration** with cite_book template support
- **External metadata** (OCLC, LCCN, VIAF, DOI, Archive.org)
- **Search and browse** by title, author, language, subject, tags
- **Text extraction** from specific page ranges

## Installation
```bash
# Clone or create project directory
mkdir -p /opt/mcp-servers/library
cd /opt/mcp-servers/library

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode
pip install -e .
```

## Configuration

Set your books directory path:
```bash
export LIBRARY_BOOKS_DIR="/home/Username/Books"
export LIBRARY_DB_PATH="/home/Username/Books/.library.db"
```

## Usage

### Initialize Database
```bash
# Create database schema
library-init-db

# Index your books directory
library-index
```

### Run MCP Server

**Stdio mode (local):**
```bash
library
```

**HTTP mode (remote):**
```bash
library --transport http --port 8080
```

## MCP Tools

### Search and Browse
- `search_library` - Search by title, author, filename, language, ISBN
- `list_by_language` - Browse books by language
- `list_by_subject` - Browse books by subject category
- `get_book_info` - Get complete metadata for a book

### Content Access
- `extract_pages` - Extract text from specific page range
- `get_wikipedia_citation` - Generate cite_book template

### Maintenance
- `index_directory` - Scan directory and update database
- `update_book_metadata` - Manually update book information

## Database Schema

See `schema.sql` for complete database structure including:
- Core book metadata (title, author, ISBN, language, etc.)
- Wikipedia citations (cite_book template fields)
- External metadata (OCLC, VIAF, WorldCat, DOI, etc.)
- File versioning (SHA256 tracking)
- Quality tracking (OCR status, missing pages, ratings)
- External libraries (OPDS catalogs)
- OCR processing (multiple engines, progress tracking)

## Development
```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## License

Apache-2.0

## Author

Peter Lemenkov <lemenkov@gmail.com>
