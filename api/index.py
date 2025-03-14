from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import re
import time
from typing import Dict
import random

app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache for transcripts
transcript_cache: Dict[str, Dict] = {}

# Simple rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 2  # seconds between requests

class YoutubeTranscriptRequest(BaseModel):
    url: str
    lang: str = "en"

@app.get("/api/py/helloFastApi")
def hello_fast_api():
    return {"message": "Hello from FastAPI"}

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    match = re.match(youtube_regex, url)
    if match:
        return match.group(6)
    
    # Try to see if the URL itself is just the video ID
    if len(url) == 11:
        return url
    
    raise ValueError("Invalid YouTube URL format")

def enforce_rate_limit():
    """Simple rate limiting function"""
    global last_request_time
    
    current_time = time.time()
    time_since_last_request = current_time - last_request_time
    
    if time_since_last_request < MIN_REQUEST_INTERVAL:
        # Add a small random delay to help avoid rate limiting
        sleep_time = MIN_REQUEST_INTERVAL - time_since_last_request + random.uniform(0.5, 2.0)
        time.sleep(sleep_time)
    
    last_request_time = time.time()

@app.post("/api/py/youtube-transcript")
async def get_youtube_transcript(request: YoutubeTranscriptRequest):
    try:
        # Extract video ID
        video_id = extract_video_id(request.url)
        
        # Check cache first
        cache_key = f"{video_id}_{request.lang}"
        if cache_key in transcript_cache:
            print(f"Cache hit for {cache_key}")
            return transcript_cache[cache_key]
        
        # Enforce rate limit before making YouTube request
        enforce_rate_limit()
        
        # Get transcript with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                
                # Try to find the requested language
                try:
                    transcript = transcript_list.find_transcript([request.lang])
                except:
                    # If the requested language isn't available, use the auto-generated one
                    try:
                        transcript = transcript_list.find_generated_transcript([request.lang])
                    except:
                        # If that fails too, just use the first available transcript
                        transcript = transcript_list.find_transcript(['en'])
                
                transcript_data = transcript.fetch()
                
                # Concatenate all text parts
                full_transcript = " ".join([item['text'] for item in transcript_data])
                
                result = {
                    "status": "success",
                    "transcript": full_transcript,
                    "video_id": video_id,
                    "language": transcript.language_code
                }
                
                # Cache the result
                transcript_cache[cache_key] = result
                return result
                
            except Exception as e:
                if attempt < max_retries - 1:
                    # Add exponential backoff delay between retries
                    wait_time = (2 ** attempt) + random.random()
                    time.sleep(wait_time)
                else:
                    raise e
            
    except NoTranscriptFound:
        return {
            "status": "no_transcript",
            "transcript": "No transcript found for this video in the specified language. Please try another language or check if the video has captions enabled.",
            "video_id": video_id if 'video_id' in locals() else None
        }
    except TranscriptsDisabled:
        return {
            "status": "disabled",
            "transcript": "Transcripts are disabled for this video.",
            "video_id": video_id if 'video_id' in locals() else None
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e),
            "transcript": "Failed to extract transcript. Please check the URL and try again."
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "transcript": "Failed to extract transcript. Please check the URL and try again."
        }