"""
Progress Routes

Endpoints for student video progress tracking and quiz submissions.
Used by the Chrome Extension for real-time progress updates.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.progress import (
    ProgressStart,
    ProgressUpdate,
    ProgressComplete,
    ProgressResponse,
    QuizSubmission,
    QuizResult,
    EnrollmentResponse,
)
from app.services import progress_service


router = APIRouter(prefix="/progress", tags=["Progress"])


@router.get(
    "/enrollments",
    response_model=list[dict],
    summary="Get user enrollments",
)
async def get_enrollments(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """
    Get all courses the current user is enrolled in.
    
    Returns list of enrollments with playlist information.
    """
    enrollments = await progress_service.get_user_enrollments(
        user=current_user,
        db=db,
    )
    
    # Convert to response format
    result = []
    for enrollment in enrollments:
        playlist = enrollment.playlist
        # Construct thumbnail URL from first video's YouTube ID
        thumbnail_url = None
        if playlist and playlist.videos:
            first_video = playlist.videos[0]
            thumbnail_url = f"https://img.youtube.com/vi/{first_video.youtube_video_id}/mqdefault.jpg"
        
        result.append({
            "id": enrollment.id,
            "playlist_id": enrollment.playlist_id,
            "is_completed": enrollment.is_completed,
            "enrolled_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
            "playlist": {
                "id": playlist.id,
                "title": playlist.title,
                "description": playlist.description,
                "thumbnail_url": thumbnail_url,
                "video_count": playlist.total_videos,
                "is_published": playlist.is_published,
                "youtube_playlist_id": playlist.Youtubelist_id,
            } if playlist else None,
        })
    
    return result


@router.post(
    "/start",
    response_model=ProgressResponse,
    summary="Start watching a video",
)
async def start_video(
    data: ProgressStart,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgressResponse:
    """
    Start watching a video.
    
    Called when the user clicks "Play" on a video.
    This creates the enrollment and progress records if they don't exist.
    
    **Lazy Linking:** This is the only endpoint that creates database rows.
    Simply viewing a playlist does NOT create any records.
    
    Args:
        data: Video ID to start watching.
        current_user: Authenticated student.
        db: Database session.
        
    Returns:
        Current progress for the video.
    """
    progress = await progress_service.start_video(
        user=current_user,
        video_id=data.video_id,
        db=db,
    )
    
    return ProgressResponse(
        video_id=progress.video_id,
        watch_status=progress.watch_status,
        seconds_watched=progress.seconds_watched,
        is_quiz_passed=progress.is_quiz_passed,
        quiz_score=progress.quiz_score,
    )


@router.post(
    "/heartbeat",
    response_model=ProgressResponse,
    summary="Update watch time",
)
async def heartbeat(
    data: ProgressUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgressResponse:
    """
    Update the watch time for a video (heartbeat).
    
    Called every 30 seconds by the Chrome Extension while user is watching.
    Tracks how many seconds the user has watched.
    
    Args:
        data: Video ID and seconds watched.
        current_user: Authenticated student.
        db: Database session.
        
    Returns:
        Updated progress for the video.
    """
    progress = await progress_service.update_watch_time(
        user=current_user,
        video_id=data.video_id,
        seconds_watched=data.seconds_watched,
        db=db,
    )
    
    return ProgressResponse(
        video_id=progress.video_id,
        watch_status=progress.watch_status,
        seconds_watched=progress.seconds_watched,
        is_quiz_passed=progress.is_quiz_passed,
        quiz_score=progress.quiz_score,
    )


@router.post(
    "/complete",
    response_model=ProgressResponse,
    summary="Mark video as complete",
)
async def complete_video(
    data: ProgressComplete,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgressResponse:
    """
    Mark a video as complete (WATCHED).
    
    Called when the user has watched ~98% of the video.
    
    **Auto-Pass:** If the video has no quiz, `is_quiz_passed` is 
    automatically set to True.
    
    Args:
        data: Video ID to mark as complete.
        current_user: Authenticated student.
        db: Database session.
        
    Returns:
        Updated progress for the video.
    """
    progress = await progress_service.complete_video(
        user=current_user,
        video_id=data.video_id,
        db=db,
    )
    
    return ProgressResponse(
        video_id=progress.video_id,
        watch_status=progress.watch_status,
        seconds_watched=progress.seconds_watched,
        is_quiz_passed=progress.is_quiz_passed,
        quiz_score=progress.quiz_score,
    )


@router.post(
    "/quiz/submit",
    response_model=QuizResult,
    summary="Submit quiz answers",
)
async def submit_quiz(
    data: QuizSubmission,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QuizResult:
    """
    Submit and grade a quiz for a video.
    
    **Grading:**
    - Compares user answers with correct answers from `video.quiz_data`
    - Score >= 75% = Passed
    
    **Answer Format:**
    ```json
    {
      "video_id": 1,
      "answers": {
        "0": "Option A",
        "1": "Option C",
        "2": "Option B"
      }
    }
    ```
    
    Args:
        data: Video ID and answers mapping.
        current_user: Authenticated student.
        db: Database session.
        
    Returns:
        Quiz result with score and pass/fail status.
    """
    progress, result = await progress_service.submit_quiz(
        user=current_user,
        video_id=data.video_id,
        answers=data.answers,
        db=db,
    )
    
    return QuizResult(**result)
