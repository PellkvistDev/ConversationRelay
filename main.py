import os
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect, ConversationRelay
import openai

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Setup FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Memory per call session
sessions = {}

@app.post("/voice")
async def voice(request: Request):
    """Twilio webhook handler for inbound or outbound call setup."""
    response = VoiceResponse()
    connect = Connect()
    connect.conversation_relay(
        url="wss://conversationrelay.onrender.com/ws",  # Replace with your Render WSS URL
        welcome_greeting="Hi! Ask me anything!",
        status_callback="https://yourdomain.onrender.com/status"  # Optional: for session cleanup
    )
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Handles ConversationRelay WebSocket messages."""
    await websocket.accept()
    session_id = None

    try:
        while True:
            message = await websocket.receive_json()
            event = message.get("event")

            if event == "start":
                session_id = message["start"]["session_id"]
                sessions[session_id] = [{"role": "system", "content": "You are a helpful assistant."}]
                print(f"Session started: {session_id}")

            elif event == "transcription":
                text = message["transcription"]["text"]
                print(f"[User]: {text}")
                sessions[session_id].append({"role": "user", "content": text})

                chat_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=sessions[session_id]
                )
                reply = chat_response.choices[0].message.content.strip()
                print(f"[Assistant]: {reply}")

                sessions[session_id].append({"role": "assistant", "content": reply})
                await websocket.send_json({"event": "response", "text": reply})

            elif event == "stop":
                print(f"Session ended: {session_id}")
                break

    except Exception as e:
        print(f"WebSocket error: {e}")

    finally:
        if session_id:
            sessions.pop(session_id, None)
        await websocket.close()

@app.post("/status")
async def cleanup_status(request: Request):
    """Optional: cleans up session when Twilio sends status callback."""
    data = await request.form()
    session_id = data.get("CallSid")
    if session_id and session_id in sessions:
        sessions.pop(session_id)
        print(f"Cleaned up session: {session_id}")
    return Response(status_code=200)
