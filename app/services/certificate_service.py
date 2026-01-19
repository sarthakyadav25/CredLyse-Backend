"""
Certificate Service

Handles certificate eligibility checking and PDF generation.
"""

import os
import uuid
from datetime import datetime
from typing import Tuple, List, Optional

from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.enrollment import Enrollment
from app.models.video_progress import VideoProgress
from app.models.certificate import Certificate
from app.models.enums import WatchStatus
from app.services.pdf_service import PdfGenerator
from app.services.storage_service import CloudinaryService


async def check_eligibility(
    user_id: uuid.UUID,
    playlist_id: int,
    db: AsyncSession,
) -> Tuple[bool, List[str]]:
    """
    Check if a user is eligible for a certificate in a course.
    
    Strict Criteria:
    1. User must be enrolled.
    2. User must have a progress record for EVERY video.
    3. Every video must be WATCHED.
    4. Every video must have is_quiz_passed=True.
    
    Args:
        user_id: User ID.
        playlist_id: Playlist ID.
        db: Database session.
        
    Returns:
        Tuple of (is_eligible, list_of_missing_requirements).
    """
    # 1. Fetch Enrollment
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.playlist_id == playlist_id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        return False, ["User is not enrolled in this course"]
    
    # 2. Fetch all videos in the playlist
    videos_result = await db.execute(
        select(Video).where(Video.playlist_id == playlist_id)
    )
    videos = list(videos_result.scalars().all())
    
    if not videos:
        return False, ["Course has no videos"]
    
    # 3. Fetch all progress records for this enrollment
    progress_result = await db.execute(
        select(VideoProgress).where(VideoProgress.enrollment_id == enrollment.id)
    )
    progress_records = list(progress_result.scalars().all())
    
    # Map video_id to progress record
    progress_map = {p.video_id: p for p in progress_records}
    
    missing = []
    
    for video in videos:
        progress = progress_map.get(video.id)
        
        if not progress:
            missing.append(f"Video '{video.title}' not started")
            continue
            
        if progress.watch_status != WatchStatus.WATCHED:
            missing.append(f"Video '{video.title}' not fully watched")
            
        if not progress.is_quiz_passed:
            missing.append(f"Video '{video.title}' quiz not passed")
            
    if missing:
        return False, missing
        
    return True, []


def _generate_and_upload_certificate(
    cert_id: str,
    user_name: str,
    course_title: str,
    issue_date: str,
) -> str:
    """
    Blocking function to generate PDF and upload to Cloudinary.
    
    This function is meant to be run in a thread pool.
    
    Args:
        cert_id: Unique certificate ID (UUID string).
        user_name: Name of the student.
        course_title: Title of the course.
        issue_date: Formatted date string.
        
    Returns:
        Cloudinary secure_url of the uploaded certificate.
    """
    # Step 1: Generate PDF with template overlay
    pdf_bytes = PdfGenerator.generate_overlay(
        student_name=user_name,
        course_name=course_title,
        issue_date=issue_date,
        cert_id=cert_id,
    )
    
    # Step 2: Upload to Cloudinary
    secure_url = CloudinaryService.upload_pdf(
        pdf_bytes=pdf_bytes,
        certificate_id=cert_id,
    )
    
    return secure_url


async def generate_certificate_pdf(
    certificate: Certificate,
    user_name: str,
    course_title: str,
) -> str:
    """
    Generate a PDF certificate using template overlay and upload to Cloudinary.
    
    Uses run_in_threadpool to avoid blocking the async event loop.
    
    Args:
        certificate: Certificate model instance.
        user_name: Name of the student.
        course_title: Title of the course.
        
    Returns:
        Cloudinary secure_url of the uploaded PDF.
    """
    # Format the issue date
    issue_date = certificate.issued_at.strftime("%B %d, %Y")
    cert_id = str(certificate.id)
    
    # Run blocking operations in threadpool
    secure_url = await run_in_threadpool(
        _generate_and_upload_certificate,
        cert_id,
        user_name,
        course_title,
        issue_date,
    )
    
    return secure_url


async def issue_certificate(
    user: User,
    playlist_id: int,
    db: AsyncSession,
) -> Certificate:
    """
    Issue a certificate to a user for a course.
    
    Flow:
    1. Check if certificate already exists (idempotency).
    2. Check eligibility (strict).
    3. Create Certificate record.
    4. Generate PDF.
    5. Update Enrollment status.
    
    Args:
        user: Student user.
        playlist_id: Course ID.
        db: Database session.
        
    Returns:
        Certificate object.
        
    Raises:
        HTTPException: 400 if not eligible.
    """
    # 1. Check existing certificate
    result = await db.execute(
        select(Certificate).where(
            Certificate.user_id == user.id,
            Certificate.playlist_id == playlist_id,
        )
    )
    existing_cert = result.scalar_one_or_none()
    
    if existing_cert:
        return existing_cert
    
    # 2. Check eligibility
    is_eligible, missing = await check_eligibility(user.id, playlist_id, db)
    
    if not is_eligible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Not eligible for certificate yet",
                "missing_requirements": missing
            }
        )
    
    # Fetch playlist for title
    playlist_result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id)
    )
    playlist = playlist_result.scalar_one_or_none()
    
    # 3. Create Certificate record
    certificate = Certificate(
        id=uuid.uuid4(),
        user_id=user.id,
        playlist_id=playlist_id,
        issued_at=datetime.utcnow(),
    )
    db.add(certificate)
    
    # 4. Generate PDF and upload to Cloudinary
    pdf_url = await generate_certificate_pdf(certificate, user.full_name, playlist.title)
    certificate.pdf_url = pdf_url
    
    # 5. Update Enrollment
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.playlist_id == playlist_id,
        )
    )
    enrollment = enrollment_result.scalar_one()
    enrollment.is_completed = True
    enrollment.certificate_url = pdf_url
    
    await db.commit()
    await db.refresh(certificate)
    
    return certificate


async def get_certificate(
    certificate_id: uuid.UUID,
    db: AsyncSession,
) -> Certificate:
    """
    Get certificate by ID.
    
    Args:
        certificate_id: UUID.
        db: Database session.
        
    Returns:
        Certificate object.
        
    Raises:
        HTTPException: 404 if not found.
    """
    result = await db.execute(
        select(Certificate).where(Certificate.id == certificate_id)
    )
    certificate = result.scalar_one_or_none()
    
    if not certificate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )
        
    return certificate
