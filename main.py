import os
import openai
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Set up OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Set up Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

@app.api_route("/voice", methods=["POST", "GET"])
async def voice(request: Request):
    """Returns TwiML to start a ConversationRelay stream."""
    response = VoiceResponse()
    connect = Connect()
    connect.conversation(service_instance_sid=os.getenv("TWILIO_CONVERSATION_SID"))
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")


@app.post("/callback")
async def callback(request: Request):
    """Triggered when a new message is sent to the conversation."""
    data = await request.json()

    try:
        msg = data["Body"]
        conversation_sid = data["ConversationSid"]
        participant_sid = data["Author"]  # "system" if from webhook, or a user ID

        # Avoid responding to our own messages
        if participant_sid == "system":
            return {"status": "ignored"}

        print(f"🗣 User: {msg}")

        # Send message to ChatGPT
        response = await chat_gpt_response(msg)

        print(f"🤖 GPT: {response}")

        # Post back to Twilio Conversation
        async with httpx.AsyncClient(auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)) as client:
            await client.post(
                f"https://conversations.twilio.com/v1/Conversations/{conversation_sid}/Messages",
                data={"Author": "system", "Body": response},
            )

    except Exception as e:
        print(f"⚠️ Error in callback: {e}")

    return {"status": "ok"}


async def chat_gpt_response(user_input: str) -> str:
    """Sends user input to ChatGPT and returns the response."""
    chat_completion = await openai.ChatCompletion.acreate(
        model="gpt-4",  # or "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": "You're a helpful voice assistant."},
            {"role": "user", "content": user_input},
        ]
    )
    return chat_completion.choices[0].message.content.strip()
