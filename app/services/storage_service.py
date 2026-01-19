"""
Storage Service

Handles file uploads to Cloudinary for certificate storage.
"""

from io import BytesIO
from typing import Optional

import cloudinary
import cloudinary.uploader

from app.core.config import settings


class CloudinaryService:
    """
    Service for uploading files to Cloudinary.
    
    Configured to upload certificates to the 'credlyse/certificates' folder.
    """
    
    _configured: bool = False
    
    @classmethod
    def _configure(cls) -> None:
        """Configure Cloudinary with credentials from settings."""
        if cls._configured:
            return
            
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        cls._configured = True
    
    @classmethod
    def upload_file(
        cls,
        file_bytes: BytesIO,
        filename: str,
        folder: str = "credlyse/certificates",
    ) -> str:
        """
        Upload a file to Cloudinary.
        
        Args:
            file_bytes: BytesIO stream of the file content.
            filename: Name for the uploaded file (without extension).
            folder: Cloudinary folder path. Default: 'credlyse/certificates'.
            
        Returns:
            The secure_url of the uploaded file.
            
        Raises:
            Exception: If upload fails.
        """
        cls._configure()
        
        # Reset stream position to beginning
        file_bytes.seek(0)
        
        result = cloudinary.uploader.upload(
            file_bytes,
            public_id=filename,
            folder=folder,
            resource_type="raw",  # For PDF files
            overwrite=True,
            invalidate=True,
        )
        
        return result["secure_url"]
    
    @classmethod
    def upload_pdf(
        cls,
        pdf_bytes: BytesIO,
        certificate_id: str,
    ) -> str:
        """
        Upload a certificate PDF to Cloudinary.
        
        Convenience wrapper for certificate uploads.
        
        Args:
            pdf_bytes: BytesIO stream of the PDF content.
            certificate_id: Unique certificate ID to use as filename.
            
        Returns:
            The secure_url of the uploaded PDF.
        """
        return cls.upload_file(
            file_bytes=pdf_bytes,
            filename=f"certificate_{certificate_id}",
            folder="credlyse/certificates",
        )
