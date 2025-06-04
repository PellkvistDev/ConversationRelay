import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect
import openai

# Initialize FastAPI
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# New OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Twilio environment vars
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_CONVERSATION_SID = os.getenv("TWILIO_CONVERSATION_SID")


@app.api_route("/voice", methods=["POST", "GET"])
async def voice(request: Request):
    """TwiML to start a Twilio ConversationRelay connection"""
    response = VoiceResponse()
    connect = Connect()
    connect.conversation(service_instance_sid=TWILIO_CONVERSATION_SID)
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


@app.post("/callback")
async def callback(request: Request):
    """Triggered when Twilio sends a new message to the conversation"""
    data = await request.json()

    try:
        msg = data["Body"]
        conversation_sid = data["ConversationSid"]
        participant_sid = data["Author"]

        # Don't reply to our own messages
        if participant_sid == "system":
            return {"status": "ignored"}

        print(f"🗣 User: {msg}")

        # ChatGPT response
        chat_response = await get_chat_response(msg)
        print(f"🤖 GPT: {chat_response}")

        # Send response back to Twilio Conversation
        async with httpx.AsyncClient(auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)) as client:
            await client.post(
                f"https://conversations.twilio.com/v1/Conversations/{conversation_sid}/Messages",
                data={"Author": "system", "Body": chat_response},
            )

    except Exception as e:
        print(f"⚠️ Error in callback: {e}")

    return {"status": "ok"}


async def get_chat_response(user_input: str) -> str:
    """Uses OpenAI ChatCompletion with new SDK"""
    chat = client.chat.completions.create(
        model="gpt-4",  # Or "gpt-4o", "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": "You're a helpful voice assistant."},
            {"role": "user", "content": user_input}
        ]
    )
    return chat.choices[0].message.content.strip()
