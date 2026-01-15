"""
Extension API Endpoints

Endpoints specifically for the Chrome extension to check playlist/enrollment status
and fetch quiz data.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import get_current_user_optional, get_current_user
from app.models.user import User
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.enrollment import Enrollment

router = APIRouter(prefix="/extension", tags=["extension"])


@router.get("/playlist-status")
async def get_playlist_status(
    youtube_playlist_id: str = Query(..., description="YouTube playlist ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Check if a YouTube playlist exists in the database and user's enrollment status.
    
    Returns playlist info, enrollment status, and video list with quiz availability.
    """
    # Find playlist by YouTube ID
    playlist_result = await db.execute(
        select(Playlist)
        .options(selectinload(Playlist.videos))
        .where(Playlist.Youtubelist_id == youtube_playlist_id)
    )
    playlist = playlist_result.scalar_one_or_none()
    
    if not playlist:
        return {
            "playlist_exists": False,
            "playlist_id": None,
            "playlist_title": None,
            "is_enrolled": False,
            "enrollment_id": None,
            "videos": [],
        }
    
    # Check enrollment if user is logged in
    is_enrolled = False
    enrollment_id = None
    
    if current_user:
        enrollment_result = await db.execute(
            select(Enrollment).where(
                Enrollment.user_id == current_user.id,
                Enrollment.playlist_id == playlist.id,
            )
        )
        enrollment = enrollment_result.scalar_one_or_none()
        if enrollment:
            is_enrolled = True
            enrollment_id = enrollment.id
    
    # Build video list
    # Sort by ID to ensure consistent ordering since 'order' field doesn't exist
    sorted_videos = sorted(playlist.videos, key=lambda v: v.id)
    
    videos = []
    for index, video in enumerate(sorted_videos):
        videos.append({
            "id": video.id,
            "youtube_video_id": video.youtube_video_id,
            "title": video.title,
            "has_quiz": video.has_quiz,
            "order": index + 1,
        })
    
    # Already sorted

    
    return {
        "playlist_exists": True,
        "playlist_id": playlist.id,
        "playlist_title": playlist.title,
        "is_enrolled": is_enrolled,
        "enrollment_id": enrollment_id,
        "videos": videos,
    }


@router.get("/video-quiz/{video_id}")
async def get_video_quiz(
    video_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Get quiz data for a specific video.
    
    Returns quiz questions if available.
    """
    video_result = await db.execute(
        select(Video).where(Video.id == video_id)
    )
    video = video_result.scalar_one_or_none()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if not video.has_quiz or not video.quiz_data:
        return {
            "has_quiz": False,
            "questions": [],
        }
    
    # Return quiz data
    questions = video.quiz_data.get("questions", [])
    
    return {
        "has_quiz": True,
        "video_id": video.id,
        "video_title": video.title,
        "questions": questions,
    }


@router.post("/enroll/{playlist_id}")
async def enroll_in_playlist(
    playlist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enroll the current user in a playlist/course.
    """
    # Check playlist exists
    playlist_result = await db.execute(
        select(Playlist)
        .options(selectinload(Playlist.videos))
        .where(Playlist.id == playlist_id)
    )
    playlist = playlist_result.scalar_one_or_none()
    
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    
    # Check if already enrolled
    existing = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current_user.id,
            Enrollment.playlist_id == playlist_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Already enrolled", "enrollment_id": existing.scalar_one_or_none().id}
    
    # Get first video for enrollment (required by current model)
    if not playlist.videos:
        raise HTTPException(status_code=400, detail="Playlist has no videos")
    
    first_video = sorted(playlist.videos, key=lambda v: v.id)[0]
    
    # Create enrollment
    enrollment = Enrollment(
        user_id=current_user.id,
        playlist_id=playlist_id,
        video_id=first_video.id,
    )
    db.add(enrollment)
    await db.commit()
    await db.refresh(enrollment)
    
    return {
        "message": "Enrolled successfully",
        "enrollment_id": enrollment.id,
    }
