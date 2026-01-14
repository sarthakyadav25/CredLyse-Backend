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
)
from app.services import progress_service


router = APIRouter(prefix="/progress", tags=["Progress"])


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
