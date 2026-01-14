"""
Analytics Service

Business logic for creator analytics and reporting.
"""

from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.playlist import Playlist
from app.models.enrollment import Enrollment
from app.models.video_progress import VideoProgress
from app.models.enums import WatchStatus
from app.schemas.analytics import StudentAnalyticsRow


async def get_course_analytics(
    creator_id: str,  # UUID as string or object
    playlist_id: int,
    db: AsyncSession,
) -> List[StudentAnalyticsRow]:
    """
    Get analytics for all students enrolled in a course.
    
    Args:
        creator_id: ID of the creator requesting analytics.
        playlist_id: Course ID.
        db: Database session.
        
    Returns:
        List of student analytics rows.
        
    Raises:
        HTTPException: 403 if user is not the creator.
        HTTPException: 404 if course not found.
    """
    # 1. Verify course ownership
    result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id)
    )
    playlist = result.scalar_one_or_none()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
        
    if str(playlist.creator_id) != str(creator_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view analytics for your own courses",
        )
    
    # 2. Fetch enrollments with related data
    # Eager load user and video_progress to avoid N+1 queries
    enrollments_result = await db.execute(
        select(Enrollment)
        .where(Enrollment.playlist_id == playlist_id)
        .options(
            selectinload(Enrollment.user),
            selectinload(Enrollment.video_progress)
        )
    )
    enrollments = list(enrollments_result.scalars().all())
    
    analytics_data = []
    total_videos = playlist.total_videos or 1  # Avoid division by zero
    
    for enrollment in enrollments:
        # Calculate completion percentage
        watched_count = sum(
            1 for p in enrollment.video_progress 
            if p.watch_status == WatchStatus.WATCHED
        )
        completion_pct = (watched_count / total_videos) * 100
        completion_pct = min(completion_pct, 100.0)  # Cap at 100%
        
        # Calculate average quiz score
        quiz_scores = [
            p.quiz_score for p in enrollment.video_progress 
            if p.quiz_score is not None
        ]
        avg_score = sum(quiz_scores) / len(quiz_scores) if quiz_scores else None
        
        row = StudentAnalyticsRow(
            student_name=enrollment.user.full_name,
            student_email=enrollment.user.email,
            enrolled_at=enrollment.created_at,
            completion_percentage=round(completion_pct, 1),
            average_quiz_score=round(avg_score, 1) if avg_score is not None else None,
            certificate_issued=enrollment.is_completed,
        )
        analytics_data.append(row)
    
    return analytics_data
