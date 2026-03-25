-- Main books table
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- File/Resource information
    filename TEXT NOT NULL,
    uri TEXT NOT NULL UNIQUE,  -- file:///path/to/book.pdf, https://..., nfs://..., ssh://...
    file_type TEXT NOT NULL,  -- pdf, djvu, epub, fb2, doc, html, jpeg-collection
    file_size INTEGER,  -- Size in bytes
    file_hash TEXT,  -- SHA256 for deduplication and change detection

    -- Bibliographic metadata (extracted or manual)
    title TEXT,
    author TEXT,
    year INTEGER,
    publisher TEXT,
    isbn TEXT,  -- ISBN-10 or ISBN-13
    language TEXT,  -- en, ru, de, cs, mixed

    -- Content information
    page_count INTEGER,
    has_ocr BOOLEAN DEFAULT 0,  -- Whether OCR text exists
    ocr_quality TEXT,  -- good, partial, poor, none

    -- Content completeness
    is_complete BOOLEAN DEFAULT 1,  -- False for partial scans, excerpts
    missing_pages TEXT,  -- e.g., "1-3,15,22-25" for damaged/missing pages
    content_type TEXT,  -- book, article, journal-excerpt, chapter, partial-scan

    -- Source tracking
    source_url TEXT,  -- Where it was downloaded from
    source_notes TEXT,  -- Additional source information

    -- Indexing timestamps
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP,  -- File modification time
    last_accessed TIMESTAMP,

    -- User annotations
    notes TEXT,
    quality_rating INTEGER  -- 1-5 stars for scan/content quality
);

-- Wikipedia citation templates (cite_book fields)
CREATE TABLE IF NOT EXISTS wikipedia_citations (
    book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,

    -- Template:Cite_book standard fields
    last TEXT,  -- Author last name
    first TEXT,  -- Author first name
    author_link TEXT,  -- Wikipedia article about author
    title TEXT,
    publisher TEXT,
    year INTEGER,
    isbn TEXT,
    pages TEXT,  -- Page range cited
    url TEXT,
    access_date TEXT,
    language TEXT,
    edition TEXT,
    location TEXT,  -- Publication location

    -- Additional citation fields
    chapter TEXT,
    translator TEXT,
    orig_year INTEGER  -- Original publication year
);

-- External metadata table
CREATE TABLE IF NOT EXISTS external_metadata (
    book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,

    -- International identifiers
    oclc_number TEXT,  -- WorldCat
    lccn TEXT,  -- Library of Congress Control Number
    doi TEXT,  -- For articles/papers

    -- Authority files (for authors)
    viaf_id TEXT,  -- Virtual International Authority File
    gnd_id TEXT,  -- German authority

    -- Digital archives
    archive_org_id TEXT,  -- Internet Archive
    google_books_id TEXT,

    -- Academic IDs (for journal articles)
    pmid TEXT,  -- PubMed
    arxiv_id TEXT,  -- arXiv preprints

    -- Catalog URLs (pre-computed for convenience)
    worldcat_url TEXT,  -- https://www.worldcat.org/oclc/...
    loc_url TEXT,  -- https://lccn.loc.gov/...

    -- Metadata freshness
    last_checked TIMESTAMP,

    -- Raw metadata JSON (for advanced use)
    raw_metadata TEXT  -- Store full API responses as JSON
);

-- Subject/topic categorization (many-to-many)
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,  -- history, philately, wine, programming, art
    parent_id INTEGER REFERENCES subjects(id),  -- For hierarchical categories
    description TEXT
);

CREATE TABLE IF NOT EXISTS book_subjects (
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, subject_id)
);

-- Free-form tags (many-to-many)
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE  -- austria-hungary, baroque, czech, russian, etc.
);

CREATE TABLE IF NOT EXISTS book_tags (
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, tag_id)
);

-- File version history (for tracking updates/changes)
CREATE TABLE IF NOT EXISTS file_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    file_hash TEXT NOT NULL,
    modified_at TIMESTAMP NOT NULL,
    change_notes TEXT,  -- e.g., "OCR corrected", "Missing pages added"

    UNIQUE(book_id, file_hash)
);

-- External library connections (OPDS catalogs, external databases)
CREATE TABLE IF NOT EXISTS external_libraries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,  -- e.g., "Internet Archive", "Library Genesis"
    type TEXT NOT NULL,  -- opds, calibre-content-server, custom-api
    base_url TEXT NOT NULL,  -- OPDS feed URL or API endpoint
    auth_type TEXT,  -- none, basic, token, api-key
    auth_credentials TEXT,  -- Encrypted credentials (if needed)
    enabled BOOLEAN DEFAULT 1,
    last_sync TIMESTAMP,
    notes TEXT
);

-- Book availability in external libraries
CREATE TABLE IF NOT EXISTS external_book_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    library_id INTEGER REFERENCES external_libraries(id) ON DELETE CASCADE,
    external_id TEXT,  -- Book ID in external library
    external_url TEXT,  -- Direct link to book in external library
    format TEXT,  -- pdf, epub, djvu, etc.
    file_size INTEGER,
    available BOOLEAN DEFAULT 1,
    last_checked TIMESTAMP,

    UNIQUE(book_id, library_id, format)
);

-- OCR processing tracking
CREATE TABLE IF NOT EXISTS ocr_processing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    ocr_engine TEXT NOT NULL,  -- tesseract, abbyy, google-vision, custom
    language TEXT,  -- Language code for OCR (en, ru, de, cs, etc.)
    status TEXT NOT NULL,  -- pending, processing, completed, failed

    -- Processing details
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    page_count INTEGER,
    pages_processed INTEGER,

    -- Output tracking
    output_format TEXT,  -- pdf-with-text, hocr, text, alto-xml
    output_uri TEXT,  -- Path/URL to OCR output

    -- Quality metrics
    confidence_score REAL,  -- Average OCR confidence (0-100)
    error_message TEXT,

    -- Resource usage
    processing_time_seconds INTEGER,

    notes TEXT,

    UNIQUE(book_id, ocr_engine)
);

-- OCR system connectors
CREATE TABLE IF NOT EXISTS ocr_systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,  -- e.g., "Local Tesseract", "Google Vision API"
    type TEXT NOT NULL,  -- local-tesseract, google-vision, abbyy-cloud, custom
    endpoint_url TEXT,  -- For cloud/API services
    auth_type TEXT,  -- none, api-key, oauth
    auth_credentials TEXT,  -- Encrypted credentials
    supported_languages TEXT,  -- JSON array of language codes
    max_file_size INTEGER,  -- Maximum file size in bytes
    enabled BOOLEAN DEFAULT 1,
    cost_per_page REAL,  -- For paid services
    notes TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_books_filename ON books(filename);
CREATE INDEX IF NOT EXISTS idx_books_uri ON books(uri);
CREATE INDEX IF NOT EXISTS idx_books_file_type ON books(file_type);
CREATE INDEX IF NOT EXISTS idx_books_file_hash ON books(file_hash);
CREATE INDEX IF NOT EXISTS idx_books_language ON books(language);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_year ON books(year);
CREATE INDEX IF NOT EXISTS idx_books_isbn ON books(isbn);
CREATE INDEX IF NOT EXISTS idx_books_content_type ON books(content_type);
CREATE INDEX IF NOT EXISTS idx_books_indexed_at ON books(indexed_at);
CREATE INDEX IF NOT EXISTS idx_books_modified_at ON books(modified_at);
CREATE INDEX IF NOT EXISTS idx_external_book_links_book ON external_book_links(book_id);
CREATE INDEX IF NOT EXISTS idx_external_book_links_library ON external_book_links(library_id);
CREATE INDEX IF NOT EXISTS idx_ocr_processing_book ON ocr_processing(book_id);
CREATE INDEX IF NOT EXISTS idx_ocr_processing_status ON ocr_processing(status);
