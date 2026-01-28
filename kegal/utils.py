import json
import urllib.request
import mimetypes
import base64
import yaml

from typing import Tuple, Optional, Dict, Callable
from pathlib import Path
from urllib.parse import urlparse


# =========
# CONSTANTS
# =========
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

IMAGE_MIME_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp'
}

PDF_MIME_TYPES = {
    '.pdf': 'application/pdf'
}

# =========
# UTILS
# =========
def load_text_from_source(source: str | Path) -> str:
    """Load text content from a file path or URL."""
    # Check if it's a URL
    parsed = urlparse(str(source))
    if parsed.scheme in ('http', 'https'):
        # Load from URL
        with urllib.request.urlopen(str(source)) as response:
            content = response.read().decode('utf-8')
    else:
        # Load from file path
        file_path = Path(source)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        content = file_path.read_text(encoding='utf-8')
    return content

def load_yml(source: str | Path):
    """Load YAML content from a file path or URL."""
    return load_text_from_source(source)

def load_json(source: str | Path):
    """Load JSON content from a file path or URL."""
    return load_text_from_source(source)

def load_contents(source: str | Path):
    """Create a Graph instance from a source (file path or URL), auto-detecting format."""
    # Simple extension detection
    extension = Path(source).suffix.lower()

    # Parse based on extension
    if extension in ['.yml', '.yaml']:
        return yaml.safe_load(load_text_from_source(source))
    elif extension in ['.json']:
        return json.loads(load_text_from_source(source))
    raise ValueError(f"Unsupported file format: {extension}. Supported formats: .yml, .yaml, .json")

def _is_base64_string(s: str) -> bool:
    """Check if a string is a valid base64 encoded string."""
    if not isinstance(s, str):
        return False

    # Base64 strings should not contain path separators or URL schemes
    if '/' in s or '\\' in s or ':' in s:
        # But could be a base64 string with padding (/)
        # Check if it looks like a path or URL
        parsed = urlparse(s)
        if parsed.scheme in ('http', 'https', 'file') or Path(s).exists():
            return False

    # Try to decode as base64
    try:
        # Remove whitespace
        s_clean = s.strip()
        # Check if it's valid base64
        decoded = base64.b64decode(s_clean, validate=True)
        # Check if it re-encodes to the same value (or close, accounting for padding)
        re_encoded = base64.b64encode(decoded).decode('utf-8')
        return len(decoded) > 0 and (re_encoded == s_clean or re_encoded.rstrip('=') == s_clean.rstrip('='))
    except Exception:
        return False

def _determine_content_type(
        path_or_uri: str | Path,
        extension_map: Dict[str, str],
        content_type_check: Optional[Callable[[str], bool]] = None,
        fallback_type: str = 'application/octet-stream'
) -> str:
    """Helper function to determine content type from various sources."""
    # Try mimetypes first
    guessed_type, _ = mimetypes.guess_type(str(path_or_uri))
    if guessed_type and (content_type_check is None or content_type_check(guessed_type)):
        return guessed_type

    # Fallback to extension mapping
    path = Path(path_or_uri)
    return extension_map.get(path.suffix.lower(), fallback_type)

def _load_binary_from_source(
        source: str | Path,
        extension_map: Dict[str, str],
        content_type_check: Optional[Callable[[str], bool]] = None,
        fallback_type: str = 'application/octet-stream',
        validator: Optional[Callable[[bytes, str | Path], None]] = None
) -> Tuple[str, str]:
    """Generic function to load binary data from file or URL and return content-type and base64."""

    # Check if source is already base64-encoded
    if isinstance(source, str) and _is_base64_string(source):
        # Validate the decoded data if validator provided
        if validator:
            try:
                decoded_data = base64.b64decode(source)
                validator(decoded_data, "base64_string")
            except Exception as e:
                raise ValueError(f"Invalid base64 data: {e}")

        # Return with fallback content type since we can't determine it from base64 alone
        return fallback_type, source.strip()

    path = Path(source)

    # Handle local file
    if path.exists() and path.is_file():
        with open(path, 'rb') as f:
            binary_data = f.read()

        # Validate data if validator provided
        if validator:
            validator(binary_data, source)

        content_type = _determine_content_type(path, extension_map, content_type_check, fallback_type)
        base64_data = base64.b64encode(binary_data).decode('utf-8')
        return content_type, base64_data

    # Handle URL
    req = urllib.request.Request(str(source), headers={'User-Agent': USER_AGENT})

    with urllib.request.urlopen(req) as response:
        content_type = response.headers.get('Content-Type', '')

        # If Content-Type header doesn't match expected type, deduce from URL
        if content_type_check is None or not content_type_check(content_type):
            content_type = _determine_content_type(source, extension_map, content_type_check, fallback_type)

        binary_data = response.read()

        # Validate data if validator provided
        if validator:
            validator(binary_data, source)

        base64_data = base64.b64encode(binary_data).decode('utf-8')
        return content_type, base64_data

def _validate_pdf_data(data: bytes, source: str | Path) -> None:
    """Validate PDF data format."""
    if len(data) == 0:
        raise ValueError(f"File {source} is empty")

    if not data.startswith(b'%PDF-'):
        raise ValueError(f"File {source} is not a valid PDF (missing PDF header)")

def load_images_to_base64(source: str | Path) -> Tuple[str, str]:
    """Load image from file path, URL, or base64 string and convert to base64."""
    return _load_binary_from_source(
        source=source,
        extension_map=IMAGE_MIME_TYPES,
        content_type_check=lambda ct: ct.startswith('image/'),
        fallback_type='image/jpeg'
    )

def load_pdfs_to_base64(source: str | Path) -> Tuple[str, str]:
    """Load PDF from file path, URL, or base64 string and convert to base64."""
    content_type, base64_data = _load_binary_from_source(
        source=source,
        extension_map=PDF_MIME_TYPES,
        content_type_check=lambda ct: ct == 'application/pdf',
        fallback_type='application/pdf',
        validator=_validate_pdf_data
    )

    # Additional validation: verify base64 can be decoded back to valid PDF
    try:
        test_decode = base64.b64decode(base64_data)
        if not test_decode.startswith(b'%PDF-'):
            raise ValueError("Base64 decode test failed - not a valid PDF")
    except Exception as e:
        raise ValueError(f"Base64 validation failed: {e}")

    return content_type, base64_data

