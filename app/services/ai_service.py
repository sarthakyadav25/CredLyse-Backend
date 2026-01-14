"""
AI Service

Handles AI-powered content analysis using OpenAI and Gemini (via LangChain).
- Primary: OpenAI with YouTube transcript
- Fallback: Gemini for direct video analysis when transcript unavailable
"""

import json
from typing import Optional, Dict, Any

from openai import AsyncOpenAI

from app.core.config import settings


# ============== OpenAI Client ==============

_openai_client: Optional[AsyncOpenAI] = None


def get_openai_client() -> AsyncOpenAI:
    """Get or create the OpenAI async client."""
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


# ============== Transcript Fetching ==============

def fetch_transcript(video_id: str) -> Optional[str]:
    """
    Fetch transcript for a YouTube video.
    
    Args:
        video_id: YouTube video ID (11 characters).
        
    Returns:
        Combined transcript text, or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        ytt_api = YouTubeTranscriptApi()
        
        # Try to fetch with preferred languages first
        try:
            transcript_list = ytt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB', 'hi', 'en-IN'])
        except Exception:
            # If preferred languages fail, try to get any available transcript
            try:
                transcript_info = ytt_api.list(video_id)
                # Get first available transcript
                first_transcript = next(iter(transcript_info))
                transcript_list = first_transcript.fetch()
            except Exception as e:
                print(f"No transcripts available for {video_id}: {e}")
                return None
        
        # Combine all segments into text
        transcript_text = " ".join(segment.text for segment in transcript_list)
        return transcript_text.strip() if transcript_text.strip() else None
    except Exception as e:
        print(f"Error fetching transcript for {video_id}: {e}")
        return None


# ============== Quiz Generation Prompts ==============

QUIZ_SYSTEM_PROMPT = """You are an educational AI assistant. Analyze the provided content and:

1. DECIDE: Is this educational content that teaches concepts? 
   - Return has_quiz=false for: intros, outros, vlogs, announcements, previews.
   - Return has_quiz=true for: lessons, tutorials, explanations, lectures.

2. GENERATE: If has_quiz=true, create exactly 5 multiple-choice questions.

Respond with valid JSON in this exact format:
{
  "has_quiz": boolean,
  "reason": "Brief explanation",
  "questions": [
    {
      "q": "Question text?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "The correct option text"
    }
  ]
}

If has_quiz is false, questions should be empty []."""


# ============== OpenAI Quiz Generation ==============

async def generate_quiz_with_openai(transcript: str) -> Dict[str, Any]:
    """
    Generate quiz from transcript using OpenAI.
    
    Args:
        transcript: The video transcript text.
        
    Returns:
        Dict containing has_quiz, reason, and questions.
    """
    client = get_openai_client()
    
    # Truncate if too long
    max_chars = 12000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "... [truncated]"
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this transcript:\n\n{transcript}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2000,
        )
        
        content = response.choices[0].message.content
        quiz_data = json.loads(content)
        
        # Validate structure
        quiz_data.setdefault("has_quiz", False)
        quiz_data.setdefault("reason", "Unknown")
        quiz_data.setdefault("questions", [])
        
        return quiz_data
        
    except Exception as e:
        print(f"OpenAI API error: {e}")
        raise


# ============== Gemini Fallback (via LangChain) ==============

async def generate_quiz_with_gemini(video_id: str, video_title: str) -> Dict[str, Any]:
    """
    Generate quiz using Gemini by analyzing the YouTube video directly.
    This is used as a fallback when transcript is unavailable.
    
    Args:
        video_id: YouTube video ID.
        video_title: Title of the video.
        
    Returns:
        Dict containing has_quiz, reason, and questions.
    """
    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY not configured, skipping fallback")
        return {
            "has_quiz": False,
            "reason": "Transcript unavailable and Gemini fallback not configured",
            "questions": []
        }
    
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
        
        # Initialize Gemini model via LangChain
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.7,
        )
        
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        prompt = f"""Analyze this YouTube video and generate a quiz if it's educational content.

Video URL: {youtube_url}
Video Title: {video_title}

{QUIZ_SYSTEM_PROMPT}

Watch/analyze the video and respond with the JSON format specified."""

        # Gemini 2.0 Flash can process video URLs
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "media",
                    "mime_type": "video/mp4",
                    "file_uri": youtube_url,
                }
            ]
        )
        
        response = await model.ainvoke([message])
        
        # Parse response - extract JSON from the response
        response_text = response.content
        
        # Try to extract JSON from response
        try:
            # Look for JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                quiz_data = json.loads(json_match.group())
            else:
                quiz_data = json.loads(response_text)
        except json.JSONDecodeError:
            print(f"Failed to parse Gemini response: {response_text[:200]}")
            quiz_data = {
                "has_quiz": False,
                "reason": "Failed to parse AI response",
                "questions": []
            }
        
        quiz_data.setdefault("has_quiz", False)
        quiz_data.setdefault("reason", "Unknown")
        quiz_data.setdefault("questions", [])
        
        return quiz_data
        
    except Exception as e:
        print(f"Gemini API error: {e}")
        return {
            "has_quiz": False,
            "reason": f"Gemini analysis failed: {str(e)}",
            "questions": []
        }


# ============== Main Analysis Pipeline ==============

async def analyze_video_content(video_id: str, video_title: str = "") -> Dict[str, Any]:
    """
    Full pipeline: fetch transcript and generate quiz.
    Falls back to Gemini if transcript unavailable.
    
    Args:
        video_id: YouTube video ID.
        video_title: Title of the video (for Gemini fallback).
        
    Returns:
        Dict with transcript, has_quiz, quiz_data, and success status.
    """
    result = {
        "success": False,
        "transcript": None,
        "has_quiz": False,
        "quiz_data": None,
        "error": None,
        "method": None,  # "openai" or "gemini"
    }
    
    # Step 1: Try to fetch transcript
    transcript = fetch_transcript(video_id)
    
    if transcript:
        # Step 2a: Use OpenAI with transcript (preferred method)
        result["transcript"] = transcript
        result["method"] = "openai"
        
        try:
            quiz_data = await generate_quiz_with_openai(transcript)
            result["has_quiz"] = quiz_data.get("has_quiz", False)
            result["quiz_data"] = quiz_data
            result["success"] = True
        except Exception as e:
            result["error"] = f"OpenAI analysis failed: {str(e)}"
    else:
        # Step 2b: Fallback to Gemini for direct video analysis
        result["method"] = "gemini"
        result["transcript"] = None
        
        try:
            quiz_data = await generate_quiz_with_gemini(video_id, video_title)
            result["has_quiz"] = quiz_data.get("has_quiz", False)
            result["quiz_data"] = quiz_data
            result["success"] = True
            
            # Note in the quiz data that this used video analysis
            if result["quiz_data"]:
                result["quiz_data"]["analysis_method"] = "video_analysis"
        except Exception as e:
            result["error"] = f"Gemini analysis failed: {str(e)}"
    
    return result
