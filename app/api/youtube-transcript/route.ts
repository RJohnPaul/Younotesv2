import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    
    // Forward the request to our FastAPI backend
    const apiUrl = process.env.NODE_ENV === "development" 
      ? "http://127.0.0.1:8000" 
      : process.env.FASTAPI_URL || "http://127.0.0.1:8000";
      
    const response = await fetch(`${apiUrl}/api/py/youtube-transcript`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || "Failed to fetch transcript" },
        { status: response.status }
      );
    }
    
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("Error in youtube-transcript API route:", error);
    return NextResponse.json(
      { error: error.message || "Internal server error" },
      { status: 500 }
    );
  }
}