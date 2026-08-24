import os
import magic
import hashlib
from typing import Dict, Any

class SecureUploadValidator:
    """
    Enforces strict security on file uploads to prevent malware ingestion,
    path traversal, and resource exhaustion.
    """
    
    def __init__(self, allowed_extensions=None, max_size_mb=10):
        self.allowed_extensions = allowed_extensions or [".png", ".jpg", ".jpeg", ".tiff"]
        self.max_size_bytes = max_size_mb * 1024 * 1024
        # Magic bytes for common medical image formats
        self.magic_signatures = {
            "image/png": b"\x89PNG\r\n\x1a\n",
            "image/jpeg": b"\xff\xd8\xff",
            "image/tiff": [b"II\x2a\x00", b"MM\x00\x2a"]
        }

    def validate(self, file_stream, filename: str) -> Dict[str, Any]:
        """
        Validates file size, extension, magic bytes, and generates a safe filename.
        """
        # 1. Size check
        file_stream.seek(0, os.SEEK_END)
        size = file_stream.tell()
        file_stream.seek(0)
        
        if size > self.max_size_bytes:
            return {"valid": False, "error": "File size exceeds 10MB limit."}
            
        # 2. Extension check
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.allowed_extensions:
            return {"valid": False, "error": f"Extension {ext} not allowed."}
            
        # 3. Magic Byte Verification (Detects renamed malware)
        header = file_stream.read(2048)
        file_stream.seek(0)
        mime = magic.from_buffer(header, mime=True)
        
        if mime not in self.magic_signatures:
            return {"valid": False, "error": f"Invalid file content type: {mime}"}
            
        # 4. Generate Deterministic/Safe Filename
        file_hash = hashlib.sha256(header).hexdigest()[:16]
        safe_fn = f"XR_{file_hash}_{os.urandom(4).hex()}{ext}"
        
        return {
            "valid": True,
            "safe_filename": safe_fn,
            "mime_type": mime,
            "size_bytes": size
        }
