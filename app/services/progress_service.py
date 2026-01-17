"""
Progress Service

Business logic for student progress tracking and quiz grading.
"""

from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.video import Video
from app.models.playlist import Playlist
from app.models.enrollment import Enrollment
from app.models.video_progress import VideoProgress
from app.models.enums import WatchStatus


async def get_video_with_playlist(
    video_id: int,
    db: AsyncSession,
) -> Video:
    """
    Get a video by ID with its playlist relationship.
    
    Args:
        video_id: Video ID.
        db: Database session.
        
    Returns:
        Video object.
        
    Raises:
        HTTPException: 404 if video not found.
    """
    result = await db.execute(
        select(Video).where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video with ID {video_id} not found",
        )
    
    return video


async def get_user_enrollments(
    user: User,
    db: AsyncSession,
) -> list[Enrollment]:
    """
    Get all enrollments for a user with their playlist data.
    
    Args:
        user: Current user.
        db: Database session.
        
    Returns:
        List of Enrollment objects with playlist relationship loaded.
    """
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Enrollment)
        .where(Enrollment.user_id == user.id)
        .options(selectinload(Enrollment.playlist))
        .order_by(Enrollment.created_at.desc())
    )
    enrollments = list(result.scalars().all())
    
    return enrollments


async def get_or_create_enrollment(
    user: User,
    playlist_id: int,
    db: AsyncSession,
) -> Enrollment:
    """
    Get existing enrollment or create a new one.
    
    Args:
        user: Current user.
        playlist_id: Playlist ID to enroll in.
        db: Database session.
        
    Returns:
        Enrollment object.
    """
    # Check for existing enrollment
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.playlist_id == playlist_id,
        )
    )
    enrollment = result.scalar_one_or_none()
    
    if enrollment:
        return enrollment
    
    # Create new enrollment
    enrollment = Enrollment(
        user_id=user.id,
        playlist_id=playlist_id,
    )
    db.add(enrollment)
    await db.flush()
    
    return enrollment


async def get_or_create_progress(
    enrollment: Enrollment,
    video_id: int,
    db: AsyncSession,
) -> VideoProgress:
    """
    Get existing video progress or create a new one.
    
    Args:
        enrollment: User's enrollment.
        video_id: Video ID.
        db: Database session.
        
    Returns:
        VideoProgress object.
    """
    result = await db.execute(
        select(VideoProgress).where(
            VideoProgress.enrollment_id == enrollment.id,
            VideoProgress.video_id == video_id,
        )
    )
    progress = result.scalar_one_or_none()
    
    if progress:
        return progress
    
    # Create new progress record
    progress = VideoProgress(
        enrollment_id=enrollment.id,
        video_id=video_id,
        watch_status=WatchStatus.NOT_STARTED,
    )
    db.add(progress)
    await db.flush()
    
    return progress


async def start_video(
    user: User,
    video_id: int,
    db: AsyncSession,
) -> VideoProgress:
    """
    Start watching a video - creates enrollment and progress if needed.
    
    Called when user clicks "Play" on a video.
    
    Args:
        user: Current user.
        video_id: Video ID to start.
        db: Database session.
        
    Returns:
        VideoProgress object.
    """
    # Get video and verify it exists
    video = await get_video_with_playlist(video_id, db)
    
    # Get or create enrollment for this playlist
    enrollment = await get_or_create_enrollment(user, video.playlist_id, db)
    
    # Get or create progress for this video
    progress = await get_or_create_progress(enrollment, video_id, db)
    
    # Update status to IN_PROGRESS if not already watched
    if progress.watch_status == WatchStatus.NOT_STARTED:
        progress.watch_status = WatchStatus.IN_PROGRESS
    
    await db.commit()
    await db.refresh(progress)
    
    return progress


async def update_watch_time(
    user: User,
    video_id: int,
    seconds_watched: int,
    db: AsyncSession,
) -> VideoProgress:
    """
    Update the watch time for a video (heartbeat).
    
    Called every 30 seconds by the Chrome Extension.
    
    Args:
        user: Current user.
        video_id: Video ID being watched.
        seconds_watched: Total seconds watched.
        db: Database session.
        
    Returns:
        Updated VideoProgress object.
        
    Raises:
        HTTPException: 404 if progress not found.
    """
    # Get video to get playlist_id
    video = await get_video_with_playlist(video_id, db)
    
    # Find the user's enrollment
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.playlist_id == video.playlist_id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not enrolled in this course. Call /start first.",
        )
    
    # Find progress record
    progress_result = await db.execute(
        select(VideoProgress).where(
            VideoProgress.enrollment_id == enrollment.id,
            VideoProgress.video_id == video_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Progress not found. Call /start first.",
        )
    
    # Update seconds watched
    progress.seconds_watched = seconds_watched
    
    # Ensure status is at least IN_PROGRESS
    if progress.watch_status == WatchStatus.NOT_STARTED:
        progress.watch_status = WatchStatus.IN_PROGRESS
    
    await db.commit()
    await db.refresh(progress)
    
    return progress


async def complete_video(
    user: User,
    video_id: int,
    db: AsyncSession,
) -> VideoProgress:
    """
    Mark a video as complete (WATCHED).
    
    Called when user has watched ~98% of the video.
    Auto-passes quiz if video has no quiz.
    
    Args:
        user: Current user.
        video_id: Video ID to complete.
        db: Database session.
        
    Returns:
        Updated VideoProgress object.
    """
    # Get video to check if it has a quiz
    video = await get_video_with_playlist(video_id, db)
    
    # Find enrollment
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.playlist_id == video.playlist_id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not enrolled in this course",
        )
    
    # Find progress
    progress_result = await db.execute(
        select(VideoProgress).where(
            VideoProgress.enrollment_id == enrollment.id,
            VideoProgress.video_id == video_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Progress not found. Call /start first.",
        )
    
    # Mark as WATCHED
    progress.watch_status = WatchStatus.WATCHED
    
    # Auto-pass if video has no quiz
    if not video.has_quiz:
        progress.is_quiz_passed = True
        progress.quiz_score = 100  # Auto-passed
    
    await db.commit()
    await db.refresh(progress)
    
    return progress


async def submit_quiz(
    user: User,
    video_id: int,
    answers: dict,
    db: AsyncSession,
) -> Tuple[VideoProgress, dict]:
    """
    Submit and grade a quiz for a video.
    
    Args:
        user: Current user.
        video_id: Video ID for the quiz.
        answers: Dict mapping question index to selected answer.
        db: Database session.
        
    Returns:
        Tuple of (VideoProgress, result_dict).
        
    Raises:
        HTTPException: 400 if video has no quiz.
    """
    # Get video with quiz data
    video = await get_video_with_playlist(video_id, db)
    
    if not video.has_quiz or not video.quiz_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This video does not have a quiz",
        )
    
    # Find enrollment and progress
    enrollment_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user.id,
            Enrollment.playlist_id == video.playlist_id,
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not enrolled in this course",
        )
    
    progress_result = await db.execute(
        select(VideoProgress).where(
            VideoProgress.enrollment_id == enrollment.id,
            VideoProgress.video_id == video_id,
        )
    )
    progress = progress_result.scalar_one_or_none()
    
    # Create progress record if it doesn't exist (user taking quiz without watching video)
    if not progress:
        progress = VideoProgress(
            enrollment_id=enrollment.id,
            video_id=video_id,
            watch_status=WatchStatus.IN_PROGRESS,  # Set to IN_PROGRESS, not WATCHED
        )
        db.add(progress)
        await db.flush()
    
    # Grade the quiz
    questions = video.quiz_data.get("questions", [])
    total_questions = len(questions)
    
    if total_questions == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quiz has no questions",
        )
    
    correct_count = 0
    for idx, question in enumerate(questions):
        user_answer = answers.get(str(idx), "")
        correct_answer = question.get("answer", "")
        
        # Case-insensitive comparison, strip whitespace
        if user_answer.strip().lower() == correct_answer.strip().lower():
            correct_count += 1
    
    # Calculate score percentage
    score = int((correct_count / total_questions) * 100)
    passed = score >= 75  # Pass threshold
    
    # Update progress
    progress.quiz_score = score
    progress.is_quiz_passed = passed
    
    # If quiz passed, check if all quizzes in the playlist are now passed
    if passed:
        await check_and_update_enrollment_completion(enrollment, video.playlist_id, db)
    
    await db.commit()
    await db.refresh(progress)
    
    result = {
        "video_id": video_id,
        "score": score,
        "passed": passed,
        "correct_count": correct_count,
        "total_questions": total_questions,
        "message": "Quiz passed! Great job!" if passed else "Quiz not passed. You need 75% to pass.",
    }
    
    return progress, result


async def check_and_update_enrollment_completion(
    enrollment: Enrollment,
    playlist_id: int,
    db: AsyncSession,
) -> bool:
    """
    Check if all quizzes in the playlist are passed and update enrollment.is_completed.
    
    Args:
        enrollment: User's enrollment.
        playlist_id: Playlist ID.
        db: Database session.
        
    Returns:
        True if enrollment is now complete, False otherwise.
    """
    from sqlalchemy.orm import selectinload
    
    # Get all videos with quizzes in the playlist
    playlist_result = await db.execute(
        select(Playlist)
        .options(selectinload(Playlist.videos))
        .where(Playlist.id == playlist_id)
    )
    playlist = playlist_result.scalar_one_or_none()
    
    if not playlist:
        return False
    
    videos_with_quizzes = [v for v in playlist.videos if v.has_quiz]
    
    if not videos_with_quizzes:
        return False
    
    # Get all progress records for this enrollment
    progress_result = await db.execute(
        select(VideoProgress).where(VideoProgress.enrollment_id == enrollment.id)
    )
    progress_records = progress_result.scalars().all()
    progress_map = {p.video_id: p for p in progress_records}
    
    # Check if all quizzes are passed
    all_passed = True
    for video in videos_with_quizzes:
        vp = progress_map.get(video.id)
        if not vp or not vp.is_quiz_passed:
            all_passed = False
            break
    
    # Update enrollment if all quizzes passed
    if all_passed and not enrollment.is_completed:
        enrollment.is_completed = True
        # Note: commit will happen in calling function
    
    return all_passed

