import os
import re
import uuid
from django.core.exceptions import ValidationError

# Allowed file extensions for dental clinical software
ALLOWED_EXTENSIONS = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'tif': 'image/tiff',
    'tiff': 'image/tiff',
    'dcm': 'application/dicom',
    'bmp': 'image/bmp'
}

# Magic byte signatures
MAGIC_NUMBERS = {
    'pdf': [b'%PDF'],
    'png': [b'\x89PNG\r\n\x1a\n'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
    'webp': [b'RIFF'],
    'tif': [b'II*\x00', b'MM\x00*'],
    'tiff': [b'II*\x00', b'MM\x00*'],
    'bmp': [b'BM'],
}

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MIN_FILE_SIZE_BYTES = 10  # Must not be empty or degenerate


def sanitize_filename(filename: str) -> str:
    """
    Strips directory paths and dangerous characters to prevent path traversal.
    """
    if not filename:
        return f"file_{uuid.uuid4().hex[:8]}"
    
    # Strip any directory path components
    clean_name = os.path.basename(filename)
    clean_name = re.sub(r'[\\/]', '', clean_name)
    # Remove control characters and non-standard symbols
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean_name)
    # Prevent multiple dots or leading dots
    clean_name = re.sub(r'\.{2,}', '.', clean_name).strip('.')
    if not clean_name:
        clean_name = f"attachment_{uuid.uuid4().hex[:8]}"
    return clean_name


def generate_unique_filename(original_filename: str) -> str:
    """
    Generates a secure, collision-free storage filename while retaining extension.
    """
    clean = sanitize_filename(original_filename)
    ext = clean.rsplit('.', 1)[-1].lower() if '.' in clean else 'bin'
    base = clean.rsplit('.', 1)[0] if '.' in clean else clean
    unique_suffix = uuid.uuid4().hex[:10]
    return f"{base}_{unique_suffix}.{ext}"


def validate_file(uploaded_file, allowed_types=None, max_size=MAX_FILE_SIZE_BYTES):
    """
    Validates file size, extension, and content magic bytes.
    Raises ValidationError on violation.
    """
    if not uploaded_file:
        raise ValidationError("No file provided.")

    # 1. Size Validation
    file_size = getattr(uploaded_file, 'size', None)
    if file_size is None and hasattr(uploaded_file, 'seek') and hasattr(uploaded_file, 'tell'):
        uploaded_file.seek(0, os.SEEK_END)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)

    if file_size is not None:
        if file_size < MIN_FILE_SIZE_BYTES:
            raise ValidationError("Uploaded file is empty (0 bytes). Please upload a valid file.")
        if file_size > max_size:
            max_mb = max_size // (1024 * 1024)
            raise ValidationError(f"File size exceeds maximum allowed limit of {max_mb}MB.")

    # 2. Extension Validation
    orig_name = sanitize_filename(getattr(uploaded_file, 'name', ''))
    if '.' not in orig_name:
        raise ValidationError("File has no extension. Please upload a valid image or PDF.")
    
    ext = orig_name.rsplit('.', 1)[-1].lower()
    allowed = allowed_types or ALLOWED_EXTENSIONS.keys()
    if ext not in allowed:
        raise ValidationError(f"Unsupported file format (.{ext}). Allowed formats: {', '.join(sorted(allowed))}.")

    # 3. Content Signature (Magic Bytes) Validation
    if ext in MAGIC_NUMBERS:
        try:
            initial_pos = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else 0
            if hasattr(uploaded_file, 'seek'):
                uploaded_file.seek(0)
            sample = uploaded_file.read(16)
            if hasattr(uploaded_file, 'seek'):
                uploaded_file.seek(initial_pos)

            signatures = MAGIC_NUMBERS[ext]
            matched = any(sample.startswith(sig) for sig in signatures)
            if ext == 'webp' and sample.startswith(b'RIFF'):
                # WEBP has RIFF at 0 and WEBP at byte 8
                if len(sample) >= 12 and sample[8:12] == b'WEBP':
                    matched = True

            if not matched:
                raise ValidationError(f"File content signature does not match extension .{ext}. File may be corrupted or disguised.")
        except ValidationError:
            raise
        except Exception:
            pass  # Fallback to extension validation if stream is not seekable

    return True

