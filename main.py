import os
import time
import json
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect
import openai

# Initialize clients
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
    form = await request.form()
    call_sid = form.get("CallSid")
    if not call_sid:
        return Response(status_code=400)
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

async def keepalive(websocket: WebSocket):
    while True:
        try:
            await websocket.send_json({"type": "ping"})
        except:
            break
        await asyncio.sleep(15)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket accepted", flush=True)
    asyncio.create_task(keepalive(websocket))

    session_id = None

    try:
        while True:
            raw = await websocket.receive()
            print("🔵 Raw frame received:", raw, flush=True)
            if "text" not in raw:
                print("🔌 WebSocket disconnect message received.", flush=True)
                break

            try:
                message = json.loads(raw["text"])
            except Exception as e:
                print(f"❗ JSON parse error: {e}", flush=True)
                continue

            msg_type = message.get("type")
            if msg_type == "setup":
                session_id = message.get("sessionId", "default_session")
                print(f"🆗 Setup session: {session_id}", flush=True)
                try:
                    with open("promt.txt", encoding="utf-8") as f:
                        system_prompt = f.read()
                except FileNotFoundError:
                    system_prompt = ""
                sessions[session_id] = {"messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "assistant", "content": greeting}
                ], "tts_start": None}

            elif msg_type == "prompt":
                text = message.get("voicePrompt", "")
                print(f"[👤 User]: {text}", flush=True)
                if not session_id or session_id not in sessions:
                    print("⚠️ No active session", flush=True)
                    continue

                # Trim history
                history = sessions[session_id]["messages"]
                history.append({"role": "user", "content": text})
                sessions[session_id]["messages"] = history[-6:]

                reply = ""
                model = "gpt-4o-mini"

                # Try streaming with fallback
                for attempt in range(2):
                    try:
                        start = time.time()
                        first_token_time = None
                        stream = await asyncio.wait_for(
                            client.chat.completions.create(
                                model=model,
                                messages=sessions[session_id]["messages"],
                                stream=True
                            ), timeout=10.0
                        )

                        async for chunk in stream:
                            delta = chunk.choices[0].delta
                            if delta and delta.content:
                                token = delta.content
                                reply += token
                                if first_token_time is None:
                                    first_token_time = time.time()
                                    print(f"⏱️ First GPT token: {first_token_time - start:.2f}s", flush=True)
                                await websocket.send_json({"type": "text", "token": token, "last": False})
                                await asyncio.sleep(0)

                        await websocket.send_json({"type": "text", "token": "", "last": True})
                        duration = time.time() - start
                        print(f"✅ GPT full time: {duration:.2f}s", flush=True)
                        break

                    except asyncio.TimeoutError:
                        print(f"⚡ GPT timeout with {model}", flush=True)
                        model = "gpt-3.5-turbo"

                print(f"[🤖 GPT]: {reply}", flush=True)
                sessions[session_id]["messages"].append({"role": "assistant", "content": reply})

            elif msg_type == "tts_start":
                sessions[session_id]["tts_start"] = time.time()
                print("🔊 TTS started", flush=True)

            elif msg_type == "tts_end":
                started = sessions[session_id].get("tts_start")
                if started:
                    print(f"🔊 TTS duration: {time.time() - started:.2f}s", flush=True)

            elif msg_type == "startOfAudio":
                print("▶️ Audio playback started", flush=True)

            elif msg_type == "endOfAudio":
                print("⏹ Audio playback ended", flush=True)

            elif msg_type == "error":
                print(f"🛑 Twilio error: {message.get('description')}", flush=True)
                break

            elif msg_type == "disconnect":
                print("🔌 Client disconnect", flush=True)
                break

    except Exception as e:
        print(f"❌ WS error: {e}", flush=True)
    finally:
        if session_id in sessions:
            sessions.pop(session_id, None)
            print(f"🧹 Cleaned session {session_id}", flush=True)

@app.post("/status")
async def cleanup_status(request: Request):
    data = await request.form()
    sid = data.get("CallSid")
    if sid and sid in sessions:
        sessions.pop(sid)
        print(f"🧼 Status cleaned: {sid}", flush=True)
    return Response(status_code=200)
