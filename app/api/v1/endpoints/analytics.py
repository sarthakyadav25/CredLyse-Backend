"""
Analytics Routes

Endpoints for creator analytics.
"""

from typing import Annotated, List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import StudentAnalyticsRow, CourseAnalyticsResponse
from app.services import analytics_service


router = APIRouter(prefix="/courses", tags=["Analytics"])


@router.get(
    "/{course_id}/analytics",
    response_model=CourseAnalyticsResponse,
    summary="Get course student analytics",
)
async def get_course_analytics(
    course_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CourseAnalyticsResponse:
    """
    Get detailed analytics for a course.
    
    **Auth:** Only the course creator can access this.
    
    **Returns:**
    - List of students enrolled
    - Progress percentage per student
    - Average quiz scores
    - Certificate status
    
    Args:
        course_id: Course ID.
        current_user: Authenticated creator.
        db: Database session.
        
    Returns:
        List of analytics rows.
    """
    return await analytics_service.get_course_analytics(
        creator_id=current_user.id,
        playlist_id=course_id,
        db=db,
    )
