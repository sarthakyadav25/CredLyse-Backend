"""
Certificate Routes

Endpoints for claiming and verifying certificates.
"""

import uuid
from typing import Annotated, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.playlist import Playlist
from app.models.enrollment import Enrollment
from app.services import certificate_service


router = APIRouter(prefix="", tags=["Certificates"])


@router.get(
    "/certificates",
    summary="List completed courses eligible for certificates",
)
async def list_certificates(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[dict]:
    """
    Get list of completed courses for the current user.
    
    Returns courses where enrollment.is_completed is True.
    This is set when all quizzes in the playlist are passed.
    """
    # Get all completed enrollments for the user with their playlists
    enrollments_result = await db.execute(
        select(Enrollment)
        .options(selectinload(Enrollment.playlist))
        .where(
            Enrollment.user_id == current_user.id,
            Enrollment.is_completed == True,  # Only completed enrollments
        )
    )
    enrollments = enrollments_result.scalars().all()
    
    completed_courses = []
    
    for enrollment in enrollments:
        playlist = enrollment.playlist
        if not playlist:
            continue
        
        completed_courses.append({
            "id": enrollment.id,
            "playlist_id": playlist.id,
            "playlist": {
                "id": playlist.id,
                "title": playlist.title,
            },
            "issued_at": enrollment.last_active_at or enrollment.created_at,
            "pdf_url": f"/api/v1/certificates/{playlist.id}/download",
        })
    
    return completed_courses


@router.get(
    "/certificates/{playlist_id}/download",
    summary="Download certificate for a completed course",
)
async def download_certificate(
    playlist_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Download certificate image for a completed course.
    
    Only available if enrollment.is_completed is True.
    """
    # Check playlist exists
    playlist_result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id)
    )
    playlist = playlist_result.scalar_one_or_none()
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Check enrollment and completion status
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current_user.id,
            Enrollment.playlist_id == playlist_id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        raise HTTPException(status_code=403, detail="Not enrolled in this playlist")
    
    if not enrollment.is_completed:
        raise HTTPException(
            status_code=403,
            detail="Course not completed. Complete all quizzes to get certificate."
        )
    
    # Enrollment is complete, return certificate
    certificate_path = Path(__file__).parent.parent.parent.parent / "resources" / "Course-Completion-Certificate.jpg"
    
    if not certificate_path.exists():
        raise HTTPException(status_code=500, detail="Certificate file not found")
    
    return FileResponse(
        path=certificate_path,
        media_type="image/jpeg",
        filename=f"Credlyse-Certificate-{playlist.title}.jpg",
    )


@router.post(
    "/courses/{course_id}/claim-certificate",
    summary="Claim course certificate",
)
async def claim_certificate(
    course_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Claim a certificate for a completed course.
    
    **Requirements:**
    - User must be enrolled.
    - All videos must be watched.
    - All quizzes must be passed.
    
    **Action:**
    - Generates a PDF certificate.
    - Marks enrollment as completed.
    - Returns the certificate URL.
    
    Args:
        course_id: Course ID.
        current_user: Authenticated student.
        db: Database session.
        
    Returns:
        Certificate details and PDF URL.
    """
    certificate = await certificate_service.issue_certificate(
        user=current_user,
        playlist_id=course_id,
        db=db,
    )
    
    return {
        "certificate_id": str(certificate.id),
        "pdf_url": certificate.pdf_url,
        "issued_at": certificate.issued_at,
        "message": "Certificate issued successfully!",
    }


@router.get(
    "/certificates/{certificate_id}",
    summary="Verify certificate",
)
async def verify_certificate(
    certificate_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Verify a certificate by ID.
    
    Public endpoint for verification links/QR codes.
    
    Args:
        certificate_id: Certificate UUID.
        db: Database session.
        
    Returns:
        Certificate details.
    """
    certificate = await certificate_service.get_certificate(certificate_id, db)
    
    return {
        "valid": True,
        "certificate_id": str(certificate.id),
        "user_id": str(certificate.user_id),
        "course_id": certificate.playlist_id,
        "issued_at": certificate.issued_at,
        "pdf_url": certificate.pdf_url,
    }
