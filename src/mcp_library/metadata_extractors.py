"""Metadata extraction from various file formats."""

import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class MetadataExtractor:
    """Extract metadata from various book file formats."""

    @staticmethod
    def detect_language(filename: str, content_sample: Optional[str] = None) -> Optional[str]:
        """Detect language from filename or content.

        Args:
            filename: The filename to analyze
            content_sample: Optional content sample for detection

        Returns:
            Language code (en, ru, de, cs) or None
        """
        # Check for Cyrillic characters in filename
        if re.search(r'[А-Яа-яЁё]', filename):
            return 'ru'

        # Check for specific language indicators in filename
        if re.search(r'\b(german|deutsch|allemand)\b', filename.lower()):
            return 'de'
        if re.search(r'\b(czech|cesky|tschechisch)\b', filename.lower()):
            return 'cs'

        # Default to English for Latin characters
        if re.search(r'[A-Za-z]', filename):
            return 'en'

        return None

    @staticmethod
    def extract_year_from_filename(filename: str) -> Optional[int]:
        """Extract publication year from filename.

        Args:
            filename: The filename to analyze

        Returns:
            Year as integer or None
        """
        # Look for 4-digit years (1800-2099)
        match = re.search(r'\b(18\d{2}|19\d{2}|20\d{2})\b', filename)
        if match:
            year = int(match.group(1))
            # Sanity check
            if 1800 <= year <= 2099:
                return year
        return None

    @staticmethod
    def extract_isbn_from_filename(filename: str) -> Optional[str]:
        """Extract ISBN from filename.

        Args:
            filename: The filename to analyze

        Returns:
            ISBN string or None
        """
        # ISBN-10: 10 digits with optional hyphens
        # ISBN-13: 13 digits with optional hyphens
        match = re.search(r'ISBN[:\s-]*((?:\d{1,5}-?){2,5}\d{1,7}[X\d])', filename, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def compute_file_hash(filepath: str) -> str:
        """Compute SHA256 hash of file.

        Args:
            filepath: Path to file

        Returns:
            SHA256 hash as hex string
        """
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def extract_metadata_from_pdf(filepath: str) -> Dict[str, Any]:
        """Extract metadata from PDF file.

        Uses pdfinfo if available, otherwise returns basic info.

        Args:
            filepath: Path to PDF file

        Returns:
            Dictionary with metadata
        """
        metadata = {}

        # Try using pdfinfo command
        try:
            import subprocess
            result = subprocess.run(
                ['pdfinfo', filepath],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        value = value.strip()

                        if key == 'title' and value:
                            metadata['title'] = value
                        elif key == 'author' and value:
                            metadata['author'] = value
                        elif key == 'pages':
                            try:
                                metadata['page_count'] = int(value)
                            except ValueError:
                                pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return metadata

    @staticmethod
    def extract_metadata_from_djvu(filepath: str) -> Dict[str, Any]:
        """Extract metadata from DjVu file.

        Uses djvused if available.

        Args:
            filepath: Path to DjVu file

        Returns:
            Dictionary with metadata
        """
        metadata = {}

        # Try using djvused command
        try:
            import subprocess
            result = subprocess.run(
                ['djvused', '-e', 'print-meta', filepath],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                # Parse DjVu metadata format
                for line in result.stdout.split('\n'):
                    if line.startswith('title'):
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            metadata['title'] = match.group(1)
                    elif line.startswith('author'):
                        match = re.search(r'"([^"]+)"', line)
                        if match:
                            metadata['author'] = match.group(1)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return metadata

    @staticmethod
    def extract_metadata_from_epub(filepath: str) -> Dict[str, Any]:
        """Extract metadata from EPUB file.

        Reads from EPUB metadata.

        Args:
            filepath: Path to EPUB file

        Returns:
            Dictionary with metadata
        """
        metadata = {}

        try:
            import zipfile
            import xml.etree.ElementTree as ET

            with zipfile.ZipFile(filepath, 'r') as epub:
                # Try to find content.opf
                for name in epub.namelist():
                    if name.endswith('.opf'):
                        with epub.open(name) as opf:
                            tree = ET.parse(opf)
                            root = tree.getroot()

                            # Define namespaces
                            ns = {
                                'dc': 'http://purl.org/dc/elements/1.1/',
                                'opf': 'http://www.idpf.org/2007/opf'
                            }

                            # Extract title
                            title_elem = root.find('.//dc:title', ns)
                            if title_elem is not None and title_elem.text:
                                metadata['title'] = title_elem.text

                            # Extract author
                            author_elem = root.find('.//dc:creator', ns)
                            if author_elem is not None and author_elem.text:
                                metadata['author'] = author_elem.text

                            # Extract ISBN
                            for identifier in root.findall('.//dc:identifier', ns):
                                if identifier.text and 'isbn' in identifier.text.lower():
                                    metadata['isbn'] = identifier.text.replace('urn:isbn:', '')

                        break
        except Exception:
            pass

        return metadata

    @staticmethod
    def extract_metadata_from_fb2(filepath: str) -> Dict[str, Any]:
        """Extract metadata from FB2 (FictionBook) file.

        Parses FB2 XML structure.

        Args:
            filepath: Path to FB2 file (may be .zip)

        Returns:
            Dictionary with metadata
        """
        metadata = {}

        try:
            import xml.etree.ElementTree as ET
            import zipfile

            # FB2 files are often zipped
            if filepath.endswith('.zip'):
                with zipfile.ZipFile(filepath, 'r') as zf:
                    for name in zf.namelist():
                        if name.endswith('.fb2'):
                            with zf.open(name) as fb2:
                                tree = ET.parse(fb2)
                                root = tree.getroot()

                                # FB2 uses specific namespaces
                                # Extract title
                                title_elem = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}book-title')
                                if title_elem is not None and title_elem.text:
                                    metadata['title'] = title_elem.text

                                # Extract author
                                author_first = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}first-name')
                                author_last = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}last-name')
                                if author_first is not None or author_last is not None:
                                    author_parts = []
                                    if author_last is not None and author_last.text:
                                        author_parts.append(author_last.text)
                                    if author_first is not None and author_first.text:
                                        author_parts.append(author_first.text)
                                    metadata['author'] = ', '.join(author_parts)

                            break
            else:
                # Direct FB2 file
                tree = ET.parse(filepath)
                root = tree.getroot()

                title_elem = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}book-title')
                if title_elem is not None and title_elem.text:
                    metadata['title'] = title_elem.text

                author_first = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}first-name')
                author_last = root.find('.//{http://www.gribuser.ru/xml/fictionbook/2.0}last-name')
                if author_first is not None or author_last is not None:
                    author_parts = []
                    if author_last is not None and author_last.text:
                        author_parts.append(author_last.text)
                    if author_first is not None and author_first.text:
                        author_parts.append(author_first.text)
                    metadata['author'] = ', '.join(author_parts)
        except Exception:
            pass

        return metadata

    @staticmethod
    def extract_all_metadata(filepath: str) -> Dict[str, Any]:
        """Extract all possible metadata from a file.

        Args:
            filepath: Path to the file

        Returns:
            Dictionary with extracted metadata
        """
        path = Path(filepath)
        filename = path.name
        file_type = path.suffix.lower().lstrip('.')

        # Basic file information
        stat = os.stat(filepath)
        metadata = {
            'filename': filename,
            'uri': f'file://{os.path.abspath(filepath)}',
            'file_type': file_type,
            'file_size': stat.st_size,
            'file_hash': MetadataExtractor.compute_file_hash(filepath),
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

        # Extract from filename
        metadata['language'] = MetadataExtractor.detect_language(filename)
        metadata['year'] = MetadataExtractor.extract_year_from_filename(filename)
        metadata['isbn'] = MetadataExtractor.extract_isbn_from_filename(filename)

        # Extract format-specific metadata
        if file_type == 'pdf':
            format_metadata = MetadataExtractor.extract_metadata_from_pdf(filepath)
        elif file_type == 'djvu':
            format_metadata = MetadataExtractor.extract_metadata_from_djvu(filepath)
        elif file_type == 'epub':
            format_metadata = MetadataExtractor.extract_metadata_from_epub(filepath)
        elif file_type in ('fb2', 'zip'):
            format_metadata = MetadataExtractor.extract_metadata_from_fb2(filepath)
        else:
            format_metadata = {}

        # Merge format-specific metadata (don't override existing)
        for key, value in format_metadata.items():
            if key not in metadata or metadata[key] is None:
                metadata[key] = value

        return metadata
