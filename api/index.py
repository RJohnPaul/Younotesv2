from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import re

### Create FastAPI instance with custom docs and openapi url
app = FastAPI(docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")

# Add CORS middleware to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/py/helloFastApi")
def hello_fast_api():
    return {"message": "Hello from FastAPI"}

class YoutubeTranscriptRequest(BaseModel):
    url: str
    lang: str = "en"

@app.post("/api/py/youtube-transcript")
async def get_youtube_transcript(request: YoutubeTranscriptRequest):
    try:
        # Extract video ID from YouTube URL
        video_id = None
        youtube_regex = (
            r'(https?://)?(www\.)?'
            '(youtube|youtu|youtube-nocookie)\.(com|be)/'
            '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
        
        match = re.match(youtube_regex, request.url)
        if match:
            video_id = match.group(6)
        else:
            # Try to see if the URL itself is just the video ID
            if len(request.url) == 11:
                video_id = request.url
        
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL format")

        # Get transcript
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
        
        # Concatenate all text parts with timestamps
        full_transcript = " ".join([item['text'] for item in transcript_data])
        
        return {
            "status": "success",
            "transcript": full_transcript,
            "video_id": video_id,
            "language": transcript.language_code
        }
            
    except NoTranscriptFound:
        return {
            "status": "no_transcript",
            "transcript": "No transcript found for this video in the specified language. Please try another language or check if the video has captions enabled.",
            "video_id": video_id if video_id else None
        }
    except TranscriptsDisabled:
        return {
            "status": "disabled",
            "transcript": "Transcripts are disabled for this video.",
            "video_id": video_id if video_id else None
        }
    except Exception as e:
        # Return a more helpful error message
        return {
            "status": "error",
            "error": str(e),
            "transcript": "Failed to extract transcript. Please check the URL and try again."
        }