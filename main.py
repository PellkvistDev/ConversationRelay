import os
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect
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
greeting = "Nämen tjenare! Fabian här."


@app.post("/voice")
async def voice(request: Request):
    """Twilio webhook handler for inbound or outbound call setup."""
    form = await request.form()
    call_sid = form.get("CallSid")
    if call_sid is None:
        return
    print(f"📞 /voice triggered for CallSid: {call_sid}", flush=True)
    response = VoiceResponse()
    connect = Connect()
    connect.conversation_relay(
        url="wss://conversationrelay.onrender.com/ws",
        welcome_greeting=greeting,
        status_callback="https://conversationrelay.onrender.com/status",
        intelligenceService=os.getenv("SID"),
        language="sv-SE",
        ttsProvider="ElevenLabs",
        voice="Azw9ahQtVs7SL0Xibr2c-0.9_0.6_0.4",
        debug="debugging",
        interruptible="any",
        welcomeGreetingInterruptible="any",
        preemptible=True,
        reportInputDuringAgentSpeech="any",
        elevenlabsTextNormalization="on"
    )
    response.append(connect)
    print(str(response), flush=True)
    return Response(content=str(response), media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket accepted", flush=True)

    session_id = None

    try:
        while True:
            raw = await websocket.receive()
            print("🔵 Raw frame received:", raw, flush=True)

            if "text" not in raw:
                print("🔌 WebSocket disconnect message received.")
                break

            try:
                import json
                message = json.loads(raw["text"])
            except Exception as e:
                print(f"❗ Error parsing JSON: {e}", flush=True)
                continue

            if message.get("type") == "setup":
                session_id = message.get("sessionId") or "default_session"
                print(f"🆗 Setup for session: {session_id}", flush=True)

                with open("promt.txt", "r", encoding="utf-8") as f:
                    system_prompt = f.read()

                print(system_prompt)
                sessions[session_id] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "assistant", "content": greeting}
                ]
                continue

            elif message.get("type") == "prompt":
                text = message.get("voicePrompt")
                print(f"[👤 User]: {text}", flush=True)

                if not session_id or session_id not in sessions:
                    print("⚠️ No session found", flush=True)
                    continue

                sessions[session_id].append({"role": "user", "content": text})
                reply = ""

                try:
                    stream = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=sessions[session_id],
                        stream=True
                    )

                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            token = delta.content
                            reply += token
                            await websocket.send_json({"type": "text", "token": token})
                except Exception as e:
                    print(f"❌ GPT stream error: {e}", flush=True)
                    continue

                print(f"[🤖 GPT]: {reply}", flush=True)
                sessions[session_id].append({"role": "assistant", "content": reply})

            elif message.get("type") == "error":
                print(f"🛑 Twilio error: {message.get('description')}", flush=True)
                break

            elif message.get("type") == "disconnect":
                print("🔌 WebSocket disconnect message received.")
                break

    except Exception as e:
        print(f"❌ WebSocket error: {e}", flush=True)

    finally:
        if session_id and session_id in sessions:
            sessions.pop(session_id, None)
            print(f"🧹 Session {session_id} cleaned up", flush=True)


@app.post("/status")
async def cleanup_status(request: Request):
    """Optional: cleans up session when Twilio sends status callback."""
    data = await request.form()
    session_id = data.get("CallSid")
    if session_id and session_id in sessions:
        sessions.pop(session_id)
        print(f"🧼 Status cleanup: {session_id}", flush=True)
    return Response(status_code=200)
