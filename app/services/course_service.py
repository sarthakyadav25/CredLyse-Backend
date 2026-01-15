"""
Course Service

Business logic for course/playlist management with YouTube API integration.
"""

import re
import uuid
from typing import Tuple, List, Dict, Any, Optional

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.playlist import Playlist
from app.models.video import Video
from app.models.enums import UserRole, PlaylistType, AnalysisStatus


# YouTube API base URL
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def parse_youtube_url(url: str) -> Tuple[str, PlaylistType]:
    """
    Parse a YouTube URL to extract the ID and determine its type.
    
    Supports:
    - Playlist URLs: https://youtube.com/playlist?list=PLxxxxxx
    - Video URLs: https://youtube.com/watch?v=xxxxxx
    - Short URLs: https://youtu.be/xxxxxx
    
    Args:
        url: YouTube URL string.
        
    Returns:
        Tuple of (youtube_id, content_type).
        
    Raises:
        ValueError: If URL format is not recognized.
    """
    # Playlist pattern
    playlist_match = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', url)
    if playlist_match:
        return playlist_match.group(1), PlaylistType.PLAYLIST
    
    # Video patterns
    video_patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in video_patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), PlaylistType.SINGLE_VIDEO
    
    raise ValueError(f"Could not parse YouTube URL: {url}")


def parse_duration(duration_str: str) -> int:
    """
    Parse ISO 8601 duration string to seconds.
    
    Example: PT1H30M45S -> 5445 seconds
    
    Args:
        duration_str: ISO 8601 duration (e.g., "PT10M30S")
        
    Returns:
        Duration in seconds.
    """
    import re
    
    hours = minutes = seconds = 0
    
    hours_match = re.search(r'(\d+)H', duration_str)
    minutes_match = re.search(r'(\d+)M', duration_str)
    seconds_match = re.search(r'(\d+)S', duration_str)
    
    if hours_match:
        hours = int(hours_match.group(1))
    if minutes_match:
        minutes = int(minutes_match.group(1))
    if seconds_match:
        seconds = int(seconds_match.group(1))
    
    return hours * 3600 + minutes * 60 + seconds


async def fetch_video_metadata(video_id: str) -> Dict[str, Any]:
    """
    Fetch metadata for a single YouTube video.
    
    Args:
        video_id: YouTube video ID.
        
    Returns:
        Dict with video metadata.
        
    Raises:
        HTTPException: If API call fails or video not found.
    """
    if not settings.YOUTUBE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="YouTube API key not configured",
        )
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{YOUTUBE_API_BASE}/videos",
            params={
                "part": "snippet,contentDetails",
                "id": video_id,
                "key": settings.YOUTUBE_API_KEY,
            },
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"YouTube API error: {response.text}",
            )
        
        data = response.json()
        
        if not data.get("items"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Video not found: {video_id}",
            )
        
        item = data["items"][0]
        snippet = item["snippet"]
        content_details = item["contentDetails"]
        
        return {
            "video_id": video_id,
            "title": snippet["title"],
            "duration_seconds": parse_duration(content_details["duration"]),
        }


async def fetch_playlist_metadata(playlist_id: str) -> Dict[str, Any]:
    """
    Fetch metadata for a YouTube playlist including all videos.
    
    Args:
        playlist_id: YouTube playlist ID.
        
    Returns:
        Dict with playlist metadata and video list.
        
    Raises:
        HTTPException: If API call fails or playlist not found.
    """
    if not settings.YOUTUBE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="YouTube API key not configured",
        )
    
    async with httpx.AsyncClient() as client:
        # Step 1: Get playlist details
        playlist_response = await client.get(
            f"{YOUTUBE_API_BASE}/playlists",
            params={
                "part": "snippet",
                "id": playlist_id,
                "key": settings.YOUTUBE_API_KEY,
            },
        )
        
        if playlist_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"YouTube API error: {playlist_response.text}",
            )
        
        playlist_data = playlist_response.json()
        
        if not playlist_data.get("items"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Playlist not found: {playlist_id}",
            )
        
        playlist_snippet = playlist_data["items"][0]["snippet"]
        
        # Step 2: Get playlist items (videos)
        videos = []
        next_page_token = None
        
        while True:
            params = {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 50,
                "key": settings.YOUTUBE_API_KEY,
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            
            items_response = await client.get(
                f"{YOUTUBE_API_BASE}/playlistItems",
                params=params,
            )
            
            if items_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"YouTube API error: {items_response.text}",
                )
            
            items_data = items_response.json()
            
            # Collect video IDs for this page
            video_ids = [
                item["snippet"]["resourceId"]["videoId"]
                for item in items_data.get("items", [])
                if item["snippet"]["resourceId"]["kind"] == "youtube#video"
            ]
            
            if video_ids:
                # Step 3: Get video details (duration)
                videos_response = await client.get(
                    f"{YOUTUBE_API_BASE}/videos",
                    params={
                        "part": "snippet,contentDetails",
                        "id": ",".join(video_ids),
                        "key": settings.YOUTUBE_API_KEY,
                    },
                )
                
                if videos_response.status_code == 200:
                    videos_data = videos_response.json()
                    
                    for vid in videos_data.get("items", []):
                        videos.append({
                            "video_id": vid["id"],
                            "title": vid["snippet"]["title"],
                            "duration_seconds": parse_duration(
                                vid["contentDetails"]["duration"]
                            ),
                        })
            
            next_page_token = items_data.get("nextPageToken")
            if not next_page_token:
                break
        
        return {
            "title": playlist_snippet["title"],
            "description": playlist_snippet.get("description", ""),
            "videos": videos,
        }


async def fetch_youtube_metadata(youtube_id: str, content_type: PlaylistType) -> Dict[str, Any]:
    """
    Fetch metadata from YouTube API.
    
    Args:
        youtube_id: YouTube playlist or video ID.
        content_type: Type of content (PLAYLIST or SINGLE_VIDEO).
        
    Returns:
        Dict containing title, description, and video list.
    """
    if content_type == PlaylistType.SINGLE_VIDEO:
        video_data = await fetch_video_metadata(youtube_id)
        return {
            "title": video_data["title"],
            "description": f"Single video course: {video_data['title']}",
            "videos": [video_data],
        }
    else:
        return await fetch_playlist_metadata(youtube_id)


async def create_course_from_url(
    url: str,
    user: User,
    db: AsyncSession,
) -> Playlist:
    """
    Create a new course from a YouTube URL.
    
    Flow:
    1. Validate user has CREATOR role
    2. Parse URL to get YouTube ID and content type
    3. Check for duplicate courses
    4. Fetch metadata from YouTube API
    5. Create Playlist and Video records
    
    Args:
        url: YouTube playlist or video URL.
        user: Current authenticated user.
        db: Database session.
        
    Returns:
        Created Playlist object with videos.
        
    Raises:
        HTTPException: 403 if user is not a creator.
        HTTPException: 400 if URL is invalid or course already exists.
    """
    # Step 1: Validate user role
    if user.role != UserRole.CREATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only creators can create courses",
        )
    
    # Step 2: Parse the YouTube URL
    try:
        youtube_id, content_type = parse_youtube_url(url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Step 3: Check for duplicate courses
    result = await db.execute(
        select(Playlist).where(Playlist.Youtubelist_id == youtube_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course with YouTube ID '{youtube_id}' already exists",
        )
    
    # Step 4: Fetch metadata from YouTube API
    metadata = await fetch_youtube_metadata(youtube_id, content_type)
    
    # Step 5: Create Playlist record
    playlist = Playlist(
        creator_id=user.id,
        Youtubelist_id=youtube_id,
        title=metadata["title"],
        description=metadata["description"],
        type=content_type,
        total_videos=len(metadata["videos"]),
        is_published=False,  # Draft by default
    )
    db.add(playlist)
    await db.flush()  # Get playlist.id
    
    # Step 6: Create Video records
    for video_data in metadata["videos"]:
        video = Video(
            playlist_id=playlist.id,
            youtube_video_id=video_data["video_id"],
            title=video_data["title"],
            duration_seconds=video_data["duration_seconds"],
            analysis_status=AnalysisStatus.PENDING,
        )
        db.add(video)
    
    await db.commit()
    await db.refresh(playlist)
    
    return playlist


async def get_published_courses(
    db: AsyncSession,
    page: int = 1,
    size: int = 10,
    search: Optional[str] = None,
) -> Tuple[List[Playlist], int]:
    """
    Get paginated list of published courses.
    
    Args:
        db: Database session.
        page: Page number (1-indexed).
        size: Items per page.
        search: Optional search term for title or creator name.
        
    Returns:
        Tuple of (playlists, total_count).
    """
    from app.models.user import User
    
    # Build base query with join for creator search
    base_query = select(Playlist).where(Playlist.is_published == True)
    
    # Apply search filter if provided
    if search:
        search_term = f"%{search.lower()}%"
        base_query = base_query.join(Playlist.creator).where(
            (func.lower(Playlist.title).like(search_term)) |
            (func.lower(User.full_name).like(search_term))
        )
    
    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0
    
    # Fetch paginated results
    offset = (page - 1) * size
    result = await db.execute(
        base_query
        .offset(offset)
        .limit(size)
        .order_by(Playlist.id.desc())
    )
    playlists = list(result.scalars().all())
    
    return playlists, total


async def get_creator_courses(
    user: User,
    db: AsyncSession,
) -> List[Playlist]:
    """
    Get all courses created by a specific user.
    
    Args:
        user: Creator user.
        db: Database session.
        
    Returns:
        List of playlists created by the user.
    """
    result = await db.execute(
        select(Playlist)
        .where(Playlist.creator_id == user.id)
        .order_by(Playlist.id.desc())
    )
    return list(result.scalars().all())


async def get_course_by_id(
    course_id: int,
    db: AsyncSession,
) -> Playlist:
    """
    Get a specific course by ID.
    
    Args:
        course_id: Playlist ID.
        db: Database session.
        
    Returns:
        Playlist object.
        
    Raises:
        HTTPException: 404 if course not found.
    """
    result = await db.execute(
        select(Playlist).where(Playlist.id == course_id)
    )
    playlist = result.scalar_one_or_none()
    
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    
    return playlist


async def publish_course(
    course_id: int,
    user: User,
    db: AsyncSession,
) -> Playlist:
    """
    Publish a course (make it visible to students).
    
    Args:
        course_id: Playlist ID.
        user: Current user (must be the creator).
        db: Database session.
        
    Returns:
        Updated playlist.
        
    Raises:
        HTTPException: 404 if not found, 403 if not owner.
    """
    playlist = await get_course_by_id(course_id, db)
    
    if playlist.creator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only publish your own courses",
        )
    
    playlist.is_published = True
    await db.commit()
    await db.refresh(playlist)
    
    return playlist
