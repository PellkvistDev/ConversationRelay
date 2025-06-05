from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, ConversationRelay
import openai
import os

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

@app.post("/voice")
async def voice(request: Request):
    response = VoiceResponse()
    connect = Connect()
    connect.conversation_relay(
        url="wss://conversationrelay.onrender.com/ws",  # Change to your deployed wss endpoint
        welcome_greeting="Hi! Ask me anything!"
    )
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_json()
            event = message.get("event")

            if event == "transcription":
                user_input = message["transcription"]["text"]

                chat_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": user_input},
                    ]
                )
                response_text = chat_response.choices[0].message.content.strip()
                await websocket.send_json({"event": "response", "text": response_text})
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await websocket.close()
