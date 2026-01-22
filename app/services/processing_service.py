"""
Processing Service

Handles background processing of course content analysis.
"""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playlist import Playlist
from app.models.video import Video
from app.models.enums import AnalysisStatus
from app.services import ai_service


async def process_course_content(
    playlist_id: int,
    db: AsyncSession,
) -> dict:
    """
    Process all pending videos in a course for AI analysis.
    
    Flow:
    1. Fetch all videos with analysis_status="PENDING"
    2. For each video:
       - Fetch transcript from YouTube
       - If failed, mark as FAILED
       - If success, call OpenAI for quiz generation
       - Update video record with results
    3. Commit changes to database
    
    Args:
        playlist_id: The playlist/course ID to process.
        db: Database session.
        
    Returns:
        Dict with processing results summary.
    """
    # Fetch playlist to verify it exists
    playlist_result = await db.execute(
        select(Playlist).where(Playlist.id == playlist_id)
    )
    playlist = playlist_result.scalar_one_or_none()
    
    if not playlist:
        return {
            "success": False,
            "error": "Playlist not found",
            "processed": 0,
            "failed": 0,
        }
    
    # Fetch all pending videos
    videos_result = await db.execute(
        select(Video).where(
            Video.playlist_id == playlist_id,
            Video.analysis_status == AnalysisStatus.PENDING,
        )
    )
    pending_videos: List[Video] = list(videos_result.scalars().all())
    
    if not pending_videos:
        return {
            "success": True,
            "message": "No pending videos to process",
            "processed": 0,
            "failed": 0,
        }
    
    processed_count = 0
    failed_count = 0
    results = []
    
    for video in pending_videos:
        video_result = {
            "video_id": video.id,
            "youtube_id": video.youtube_video_id,
            "title": video.title,
            "status": None,
            "error": None,
            "method": None,
        }
        
        try:
            # Analyze video content (transcript + AI, or Gemini fallback)
            analysis = await ai_service.analyze_video_content(
                video_id=video.youtube_video_id,
                video_title=video.title,
                duration_seconds=video.duration_seconds,
            )
            
            video_result["method"] = analysis.get("method")
            
            if analysis["success"]:
                # Check if we got valid quiz data (not just error messages)
                quiz_data = analysis.get("quiz_data")
                has_valid_quiz = (
                    quiz_data 
                    and quiz_data.get("has_quiz") 
                    and len(quiz_data.get("questions", [])) > 0
                )
                
                # Only save if we have transcript OR valid quiz
                if analysis.get("transcript") or has_valid_quiz:
                    video.transcript_text = analysis.get("transcript")
                    video.has_quiz = has_valid_quiz
                    # Only save quiz_data if it has actual questions
                    video.quiz_data = quiz_data if has_valid_quiz else None
                    video.analysis_status = AnalysisStatus.COMPLETED
                    
                    processed_count += 1
                    video_result["status"] = "completed"
                    video_result["has_quiz"] = has_valid_quiz
                else:
                    # No transcript and no valid quiz = failed
                    video.analysis_status = AnalysisStatus.FAILED
                    video.quiz_data = None  # Keep null, don't save error data
                    failed_count += 1
                    video_result["status"] = "failed"
                    video_result["error"] = "No transcript or quiz data available"
            else:
                # Mark as failed - don't save any error data to quiz_data
                video.analysis_status = AnalysisStatus.FAILED
                video.quiz_data = None  # Explicitly keep null
                failed_count += 1
                video_result["status"] = "failed"
                video_result["error"] = analysis.get("error", "Unknown error")
                
        except Exception as e:
            # Handle unexpected errors - don't save error to quiz_data
            video.analysis_status = AnalysisStatus.FAILED
            video.quiz_data = None
            failed_count += 1
            video_result["status"] = "failed"
            video_result["error"] = str(e)
        
        results.append(video_result)
    
    # Commit all changes
    await db.commit()
    
    return {
        "success": True,
        "playlist_id": playlist_id,
        "playlist_title": playlist.title,
        "total_pending": len(pending_videos),
        "processed": processed_count,
        "failed": failed_count,
        "details": results,
    }


async def get_analysis_status(
    playlist_id: int,
    db: AsyncSession,
) -> dict:
    """
    Get the analysis status summary for a playlist.
    
    Args:
        playlist_id: The playlist/course ID.
        db: Database session.
        
    Returns:
        Dict with counts by status.
    """
    videos_result = await db.execute(
        select(Video).where(Video.playlist_id == playlist_id)
    )
    videos = list(videos_result.scalars().all())
    
    status_counts = {
        "pending": 0,
        "completed": 0,
        "failed": 0,
        "total": len(videos),
        "with_quiz": 0,
    }
    
    for video in videos:
        if video.analysis_status == AnalysisStatus.PENDING:
            status_counts["pending"] += 1
        elif video.analysis_status == AnalysisStatus.COMPLETED:
            status_counts["completed"] += 1
            if video.has_quiz:
                status_counts["with_quiz"] += 1
        elif video.analysis_status == AnalysisStatus.FAILED:
            status_counts["failed"] += 1
    
    return status_counts
