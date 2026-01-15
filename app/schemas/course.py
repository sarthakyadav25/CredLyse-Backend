"""
Course Schemas

Pydantic models for playlist and video request/response validation.
"""

from datetime import datetime
from typing import Optional, List
import uuid

from pydantic import BaseModel, Field, HttpUrl

from app.models.enums import PlaylistType, AnalysisStatus


# ============== Video Schemas ==============

class VideoBase(BaseModel):
    """Base schema for video data."""
    
    title: str = Field(..., description="Video title")
    youtube_video_id: str = Field(..., description="YouTube video ID")
    duration_seconds: int = Field(default=0, description="Video duration in seconds")


class VideoResponse(VideoBase):
    """Schema for video response."""
    
    id: int
    playlist_id: int
    has_quiz: bool
    analysis_status: AnalysisStatus
    quiz_data: Optional[dict] = Field(default=None, description="Quiz questions and answers")
    
    model_config = {"from_attributes": True}


# ============== Playlist Schemas ==============

class PlaylistCreate(BaseModel):
    """Schema for creating a new playlist/course."""
    
    youtube_url: str = Field(..., description="YouTube playlist or video URL")
    type: PlaylistType = Field(
        default=PlaylistType.PLAYLIST,
        description="Type of content: PLAYLIST or SINGLE_VIDEO"
    )


class PlaylistBase(BaseModel):
    """Base schema for playlist data."""
    
    title: str
    description: Optional[str] = None
    Youtubelist_id: str
    type: PlaylistType
    total_videos: int
    is_published: bool


class PlaylistResponse(PlaylistBase):
    """Schema for playlist response with nested videos."""
    
    id: int
    creator_id: uuid.UUID
    videos: List[VideoResponse] = []
    
    model_config = {"from_attributes": True}


class PlaylistListResponse(BaseModel):
    """Schema for paginated playlist list."""
    
    items: List[PlaylistResponse]
    total: int
    page: int
    size: int
    pages: int
