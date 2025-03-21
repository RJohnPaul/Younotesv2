from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import re
import time
from typing import Dict
import random
import asyncio
import os
from urllib.parse import urlparse, parse_qs

app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache for transcripts (will reset on service restart)
transcript_cache: Dict[str, Dict] = {}

# More aggressive rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 5  # seconds between requests
BACKOFF_MULTIPLIER = 1.5  # increase delay after each rate limit error

# Track consecutive errors to implement dynamic backoff
consecutive_errors = 0
current_backoff = MIN_REQUEST_INTERVAL

class YoutubeTranscriptRequest(BaseModel):
    url: str
    lang: str = "en"

@app.get("/api/py/youtube-transcript")
async def get_transcript_docs():
    """Handle GET requests to the transcript endpoint with usage instructions"""
    return {
        "message": "This endpoint requires a POST request with JSON body containing 'url' and optional 'lang' parameters",
        "example": {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "lang": "en"
        },
        "usage": "Send a POST request to this endpoint with the above JSON structure"
    }

@app.get("/api/py/helloFastApi")
def hello_fast_api():
    return {"message": "Hello from FastAPI"}

@app.get("/")
def root():
    return {
        "message": "YouNotes API is running",
        "endpoints": {
            "/api/py/youtube-transcript": "POST: Get YouTube transcript",
            "/api/py/helloFastApi": "GET: Test if API is working",
            "/api/py/docs": "GET: API documentation"
        }
    }

def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL using multiple methods"""
    # Method 1: Regex pattern matching
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    match = re.match(youtube_regex, url)
    if match and match.group(6):
        return match.group(6)
    
    # Method 2: Parse URL query parameters
    try:
        parsed_url = urlparse(url)
        if 'youtube.com' in parsed_url.netloc:
            query = parse_qs(parsed_url.query)
            if 'v' in query:
                return query['v'][0]
    except:
        pass
    
    # Method 3: Check for youtu.be format
    try:
        if 'youtu.be' in url:
            path = urlparse(url).path
            if path and len(path) > 1:
                return path[1:]  # Remove leading slash
    except:
        pass
    
    # Method 4: Check if the string itself is just the video ID (11 chars)
    if re.match(r'^[A-Za-z0-9_-]{11}$', url):
        return url
    
    raise ValueError("Invalid YouTube URL format. Please provide a valid YouTube URL.")

async def enforce_rate_limit():
    """Dynamic rate limiting with exponential backoff"""
    global last_request_time, consecutive_errors, current_backoff
    
    current_time = time.time()
    time_since_last_request = current_time - last_request_time
    
    # Calculate delay based on consecutive errors
    if consecutive_errors > 0:
        # Exponential backoff
        delay = current_backoff * (BACKOFF_MULTIPLIER ** consecutive_errors)
        delay = min(delay, 30)  # Cap at 30 seconds
    else:
        delay = MIN_REQUEST_INTERVAL
    
    if time_since_last_request < delay:
        # Add jitter to the delay
        sleep_time = delay - time_since_last_request + random.uniform(1.0, 3.0)
        await asyncio.sleep(sleep_time)
    
    last_request_time = time.time()

@app.post("/api/py/youtube-transcript")
async def get_youtube_transcript(request: YoutubeTranscriptRequest):
    global consecutive_errors, current_backoff
    
    try:
        # Extract video ID with improved error handling
        try:
            video_id = extract_video_id(request.url)
        except ValueError as e:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "error": str(e),
                    "transcript": None
                }
            )
        
        # Check cache first (avoid YouTube requests if possible)
        cache_key = f"{video_id}_{request.lang}"
        if cache_key in transcript_cache:
            print(f"Cache hit for {cache_key}")
            # Reset error counter on successful cache hit
            consecutive_errors = 0
            return transcript_cache[cache_key]
        
        # Enforce rate limit before making YouTube request
        await enforce_rate_limit()
        
        # Get transcript with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Log the attempt for debugging
                print(f"Fetching transcript for {video_id}, attempt {attempt+1}/{max_retries}")
                
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
                # Reset error counter on success
                consecutive_errors = 0
                return result
                
            except Exception as e:
                if "Too Many Requests" in str(e):
                    # Rate limited by YouTube - increase backoff
                    consecutive_errors += 1
                    current_backoff = min(current_backoff * BACKOFF_MULTIPLIER, 20)
                    
                    # Add a much longer delay when rate limited
                    wait_time = (4 ** attempt) + random.uniform(3, 7)
                    print(f"Rate limited by YouTube, waiting {wait_time} seconds before retry")
                    await asyncio.sleep(wait_time)
                    
                    if attempt == max_retries - 1:
                        return {
                            "status": "rate_limited",
                            "error": "YouTube rate limit exceeded. Please try again in a few minutes.",
                            "transcript": None
                        }
                elif attempt < max_retries - 1:
                    # Add exponential backoff delay between retries for other errors
                    wait_time = (2 ** attempt) + random.random()
                    await asyncio.sleep(wait_time)
                else:
                    raise e
            
    except NoTranscriptFound:
        return {
            "status": "no_transcript",
            "transcript": "No transcript found for this video in the specified language. Please try another language or check if the video has captions enabled.",
            "video_id": video_id
        }
    except TranscriptsDisabled:
        return {
            "status": "disabled",
            "transcript": "Transcripts are disabled for this video.",
            "video_id": video_id
        }
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e),
            "transcript": None
        }
    except Exception as e:
        consecutive_errors += 1
        error_msg = str(e)
        
        if "Too Many Requests" in error_msg:
            return {
                "status": "rate_limited",
                "error": "YouTube rate limit exceeded. Please try again in a few minutes.",
                "transcript": None,
                "retry_after": current_backoff * (BACKOFF_MULTIPLIER ** consecutive_errors)
            }
        
        return {
            "status": "error",
            "error": error_msg,
            "transcript": "Failed to extract transcript. Please check the URL and try again."
        }

# Middleware to handle errors
@app.middleware("http")
async def add_error_handling(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": f"Server error: {str(e)}",
                "message": "An unexpected error occurred processing your request."
            }
        )