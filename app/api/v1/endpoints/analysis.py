"""
Analysis Routes

Endpoints for triggering content analysis on courses.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.services import course_service
from app.services import processing_service


router = APIRouter(prefix="/courses", tags=["Analysis"])


@router.post(
    "/{course_id}/analyze",
    summary="Trigger AI analysis for course videos",
)
async def analyze_course(
    course_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Trigger AI content analysis for all pending videos in a course.
    
    **Process:**
    1. Fetches transcript from YouTube for each video
    2. Sends transcript to OpenAI for analysis
    3. Generates quiz questions for educational content
    4. Updates video records with results
    
    **Requirements:**
    - User must be the course creator
    - Videos must have analysis_status="PENDING"
    
    Args:
        course_id: The playlist/course ID.
        current_user: Authenticated user (must be owner).
        db: Database session.
        
    Returns:
        Processing results with success/failure counts.
    """
    # Verify the course exists and user is the creator
    course = await course_service.get_course_by_id(course_id, db)
    
    if course.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only analyze your own courses",
        )
    
    # Process all pending videos
    result = await processing_service.process_course_content(
        playlist_id=course_id,
        db=db,
    )
    
    return result


@router.get(
    "/{course_id}/analysis-status",
    summary="Get analysis status for a course",
)
async def get_analysis_status(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Get the analysis status summary for a course.
    
    Returns counts of videos by analysis status (pending, completed, failed).
    
    Args:
        course_id: The playlist/course ID.
        db: Database session.
        
    Returns:
        Status counts and summary.
    """
    # Verify course exists
    await course_service.get_course_by_id(course_id, db)
    
    status = await processing_service.get_analysis_status(
        playlist_id=course_id,
        db=db,
    )
    
    return {
        "course_id": course_id,
        **status,
    }
