import { NextResponse } from "next/server";

export const maxDuration = 30; // Increase timeout limit to 30 seconds (requires Vercel Pro plan)

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const apiUrl = "https://younotesv2.onrender.com";
    
    console.log("Fetching transcript from:", apiUrl);
    
    // Add timeout to fetch request
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 25000); // 25 second timeout
    
    try {
      const response = await fetch(`${apiUrl}/api/py/youtube-transcript`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId); // Clear timeout if fetch completes
      
      const data = await response.json();
      
      if (!response.ok) {
        return NextResponse.json(
          { error: data.detail || "Failed to fetch transcript" },
          { status: response.status }
        );
      }
      
      return NextResponse.json(data);
    } catch (fetchError: any) {
      clearTimeout(timeoutId);
      if (fetchError.name === 'AbortError') {
        // This was a timeout
        return NextResponse.json(
          { error: "Backend service took too long to respond. It might be waking up from sleep mode. Please try again." },
          { status: 504 }
        );
      }
      throw fetchError;
    }
  } catch (error: any) {
    console.error("Error in youtube-transcript API route:", error);
    return NextResponse.json(
      { error: error.message || "Internal server error" },
      { status: 500 }
    );
  }
}