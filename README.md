# Syntiox DL API - Documentation

Welcome to the Syntiox DL API! This API allows you to extract high-quality video and audio download links from YouTube.

## Base URL
Production Server: `https://dl-production-ac4e.up.railway.app`

## Authentication
The API requires an `X-API-KEY` header for all requests to the `/info` endpoint.
**API Key:** `cDlzdjlmODdoOWY4aGQ3Zjk4N2RmaGQ5cGdmaGQ5YWZkOThmNzg=`

---

## 1. Get Video Information & Download Links
**Endpoint:** `/info`
**Method:** `POST`

### JavaScript Example (Fetch)
```javascript
const apiUrl = "https://dl-production-ac4e.up.railway.app/info";
const apiKey = "cDlzdjlmODdoOWY4aGQ3Zjk4N2RmaGQ5cGdmaGQ5YWZkOThmNzg=";

async function getVideoInfo(youtubeUrl) {
    try {
        const response = await fetch(apiUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-API-KEY": apiKey
            },
            body: JSON.stringify({ url: youtubeUrl })
        });

        if (!response.ok) {
            const errorData = await response.json();
            console.error("API Error:", errorData.detail);
            return;
        }

        const data = await response.json();
        console.log("Success! Data received:", data);

        // Accessing the download links
        const videoTitle = data.title;
        const bestVideoUrl = data.best_video_download_url; // Direct mp4 video link
        const bestAudioUrl = data.audio_download_url;      // Direct mp3/m4a audio link

        console.log("Title:", videoTitle);
        console.log("Best Video URL:", bestVideoUrl);
        console.log("Best Audio URL:", bestAudioUrl);

    } catch (error) {
        console.error("Network Error:", error);
    }
}

// Test the function
getVideoInfo("https://youtu.be/wc4p8DASvU4");
```

### Expected JSON Response
When you make a successful request, the API will return a JSON object like this:

```json
{
    "type": "video",
    "title": "Mandari - CHIRA BOY | Official Music Video",
    "thumb": "https://i.ytimg.com/vi_webp/wc4p8DASvU4/maxresdefault.webp",
    "duration": 234,
    "uploader": "Chira Boy",
    "formats": [
        {
            "id": "18",
            "res": "360p",
            "ext": "mp4",
            "download_url": "https://dl-production-ac4e.up.railway.app/stream?token=eyJhb..."
        }
    ],
    "best_video_download_url": "https://dl-production-ac4e.up.railway.app/stream?token=eyJhbGc...",
    "audio_download_url": "https://dl-production-ac4e.up.railway.app/stream?token=eyJhbGciOiJIUz..."
}
```

### Important Notes on the Links (Streaming Proxy)
- The download URLs (`best_video_download_url`, `audio_download_url`, and the URLs inside the `formats` array) are **secure proxy links** routed through our server.
- They are **Single-Use** tokens. Once a download is started, the link cannot be copied and reused by someone else.
- The tokens automatically **expire after 20 minutes**.
- When accessing the `audio_download_url`, the server automatically extracts the pure Audio stream using `ffmpeg` and serves it as an `audio.mp3` file!
