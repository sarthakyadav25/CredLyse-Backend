"""
Course Routes

Endpoints for course/playlist management.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.schemas.course import (
    PlaylistCreate,
    PlaylistResponse,
    PlaylistListResponse,
)
from app.services import course_service



router = APIRouter(prefix="/courses", tags=["Courses"])


@router.post(
    "/",
    response_model=PlaylistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new course from YouTube URL",
)
async def create_course(
    course_data: PlaylistCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlaylistResponse:
    """
    Create a new course from a YouTube playlist or video URL.
    
    **Requirements:**
    - User must have CREATOR role
    - YouTube URL must be valid
    - Course must not already exist
    
    **Flow:**
    1. Parse the YouTube URL to extract ID
    2. Fetch metadata (title, videos)
    3. Create Playlist and Video records
    
    Args:
        course_data: YouTube URL and content type.
        current_user: Authenticated user (must be CREATOR).
        db: Database session.
        
    Returns:
        Created playlist with nested videos.
    """
    playlist = await course_service.create_course_from_url(
        url=course_data.youtube_url,
        user=current_user,
        db=db,
    )
    return playlist


@router.get(
    "/",
    response_model=PlaylistListResponse,
    summary="List all published courses",
)
async def list_courses(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by title or creator name"),
) -> PlaylistListResponse:
    """
    Get a paginated list of all published courses.
    
    This endpoint is public (no authentication required).
    Only published courses are returned.
    
    Args:
        db: Database session.
        page: Page number (1-indexed).
        size: Number of items per page.
        search: Optional search term for title or creator name.
        
    Returns:
        Paginated list of published courses.
    """
    playlists, total = await course_service.get_published_courses(
        db=db,
        page=page,
        size=size,
        search=search,
    )
    
    pages = (total + size - 1) // size  # Ceiling division
    
    return PlaylistListResponse(
        items=playlists,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get(
    "/my-created",
    response_model=list[PlaylistResponse],
    summary="List courses created by current user",
)
async def list_my_courses(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PlaylistResponse]:
    """
    Get all courses created by the authenticated user.
    
    **Requirements:**
    - User must be authenticated
    - Typically used by CREATOR role users
    
    Args:
        current_user: Authenticated user.
        db: Database session.
        
    Returns:
        List of courses created by the user.
    """
    playlists = await course_service.get_creator_courses(
        user=current_user,
        db=db,
    )
    return playlists


@router.get(
    "/{course_id}",
    response_model=PlaylistResponse,
    summary="Get course details",
)
async def get_course(
    course_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlaylistResponse:
    """
    Get detailed information about a specific course.
    
    This endpoint is public (no authentication required).
    Returns the playlist with all nested videos.
    
    Args:
        course_id: The playlist/course ID.
        db: Database session.
        
    Returns:
        Course details with video list.
    """
    playlist = await course_service.get_course_by_id(
        course_id=course_id,
        db=db,
    )
    return playlist


@router.post(
    "/{course_id}/publish",
    response_model=PlaylistResponse,
    summary="Publish a course",
)
async def publish_course(
    course_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlaylistResponse:
    """
    Publish a course to make it visible to students.
    
    **Requirements:**
    - User must be the course creator
    
    Args:
        course_id: The playlist/course ID.
        current_user: Authenticated user (must be owner).
        db: Database session.
        
    Returns:
        Updated course with is_published=True.
    """
    playlist = await course_service.publish_course(
        course_id=course_id,
        user=current_user,
        db=db,
    )
    return playlist
