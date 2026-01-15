
import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.database import get_session_maker
from app.models.playlist import Playlist
from app.models.video import Video

async def check_playlist():
    async_session = get_session_maker()
    async with async_session() as db:
        youtube_playlist_id = "PLZoTAELRMXVM8Pf4U67L4UuDRgV4TNX9D"
        print(f"Checking Playlist: {youtube_playlist_id}")
        
        result = await db.execute(
            select(Playlist)
            .options(selectinload(Playlist.videos))
            .where(Playlist.Youtubelist_id == youtube_playlist_id)
        )
        playlist = result.scalar_one_or_none()
        
        if not playlist:
            print("❌ Playlist NOT FOUND in DB")
            return

        print(f"✅ Playlist Found: {playlist.title} (ID: {playlist.id})")
        print(f"Videos count: {len(playlist.videos)}")
        
        for video in playlist.videos:
            print(f"  - Video: {video.title[:30]}... (ID: {video.youtube_video_id}) | Has Quiz: {video.has_quiz}")
            if video.youtube_video_id == "fZM3oX4xEyg":
                print(f"    👉 THIS IS THE CURRENT VIDEO. Has Quiz: {video.has_quiz}")
                if video.has_quiz and video.quiz_data:
                    print(f"    ✅ Quiz Data Present: {len(video.quiz_data.get('questions', []))} questions")
                else:
                    print(f"    ❌ Quiz Data Missing or Empty")

if __name__ == "__main__":
    asyncio.run(check_playlist())
