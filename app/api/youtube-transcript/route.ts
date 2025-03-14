import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    
    // Forward the request to our FastAPI backend
    let apiUrl = process.env.NODE_ENV === "development" 
      ? "http://127.0.0.1:8000" 
      : process.env.NEXT_PUBLIC_FASTAPI_URL;
    
    // Use hardcoded fallback if environment variable is not set
    if (!apiUrl) {
      console.error("FASTAPI_URL environment variable is undefined, using fallback URL");
      apiUrl = "https://younotesv2.onrender.com";
    }
    
    console.log("Using API URL:", apiUrl); // Debug log
    
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