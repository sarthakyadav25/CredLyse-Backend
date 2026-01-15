"""
Progress Schemas

Pydantic models for video progress tracking and quiz submissions.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.models.enums import WatchStatus


class ProgressStart(BaseModel):
    """Schema for starting video playback."""
    
    video_id: int = Field(..., description="Video ID to start watching")


class ProgressUpdate(BaseModel):
    """Schema for updating watch time (heartbeat)."""
    
    video_id: int = Field(..., description="Video ID being watched")
    seconds_watched: int = Field(..., ge=0, description="Total seconds watched")


class ProgressComplete(BaseModel):
    """Schema for marking video as complete."""
    
    video_id: int = Field(..., description="Video ID to mark as complete")


class QuizSubmission(BaseModel):
    """Schema for quiz answer submission."""
    
    video_id: int = Field(..., description="Video ID for the quiz")
    answers: Dict[str, str] = Field(
        ..., 
        description="Question index to selected answer mapping (e.g., {'0': 'Option A'})"
    )


class ProgressResponse(BaseModel):
    """Schema for progress response."""
    
    video_id: int
    watch_status: WatchStatus
    seconds_watched: int
    is_quiz_passed: bool
    quiz_score: Optional[int] = None
    
    model_config = {"from_attributes": True}


class QuizResult(BaseModel):
    """Schema for quiz submission result."""
    
    video_id: int
    score: int  # Percentage
    passed: bool
    correct_count: int
    total_questions: int
    message: str


class EnrollmentResponse(BaseModel):
    """Schema for enrollment response."""
    
    id: int
    playlist_id: int
    is_completed: bool
    created_at: Optional[str] = None
    # Nested playlist info
    playlist: Optional[dict] = None
    
    model_config = {"from_attributes": True}

