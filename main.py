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
greeting = "Nämen tjenare! David här."

@app.post("/voice")
async def voice(request: Request):
    """Twilio webhook handler for inbound or outbound call setup."""
    print("Connecting something")
    response = VoiceResponse()
    connect = Connect()
    connect.conversation_relay(
        url="wss://conversationrelay.onrender.com/ws",  # Replace with your Render WSS URL
        welcome_greeting=greeting,
        status_callback="https://conversationrelay.onrender.com/status",  # Optional: for session cleanup
        intelligenceService=os.getenv("SID"),
        language="sv-SE",
        debug="debugging"
    )
    response.append(connect)
    print(str(response))
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket accepted")

    session_id = None

    try:
        while True:
            message = await websocket.receive_json()
            print("🔵 Raw message:", message)

            if message.get("type") == "setup":
                session_id = message.get("sessionId") or "default_session"
                print(f"🆗 Setup message received, session: {session_id}")
                # Initialize session memory
                with open("promt.txt", "r", encoding="utf-8") as f:
                    system_prompt = f.read()
                sessions[session_id] = [{"role": "system", "content": system_prompt}]
                sessions[session_id].append({"role": "assistant", "content": greeting})
                continue

            elif message.get("type") == "prompt":
                text = message.get("voicePrompt")
                print(f"[👤 User]: {text}")
                sessions[session_id].append({"role": "user", "content": text})

                chat_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=sessions[session_id]
                )
                reply = chat_response.choices[0].message.content.strip()
                print(f"[🤖 GPT]: {reply}")

                sessions[session_id].append({"role": "assistant", "content": reply})
                await websocket.send_json({"type": "text", "token": reply})

            elif message.get("type") == "error":
                print(f"🛑 Recived error from Twilio: {message.get('description')}")
                break
            continue

    except Exception as e:
        print(f"❌ WebSocket error: {e}")

    finally:
        if session_id and session_id in sessions:
            sessions.pop(session_id, None)


@app.post("/status")
async def cleanup_status(request: Request):
    """Optional: cleans up session when Twilio sends status callback."""
    data = await request.form()
    session_id = data.get("CallSid")
    if session_id and session_id in sessions:
        sessions.pop(session_id)
        print(f"Cleaned up session: {session_id}")
    return Response(status_code=200)
