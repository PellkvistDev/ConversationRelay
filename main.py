import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
import openai
import uvicorn

# Load environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_INSTRUCTIONS = "Du är en hjälpsam AI-assistent som svarar tydligt på svenska."

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Initialize FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

@app.api_route("/voice", methods=["GET", "POST"])
async def voice(request: Request):
    """
    Called by Twilio when someone calls your Twilio number.
    Connects to ConversationRelay.
    """
    print("📞 Incoming call")

    response = VoiceResponse()
    connect = Connect()
    connect.conversation(service_sid="GAb47c4f517fb8e33ad7329fa51260d9b9")
    response.append(connect)

    return Response(content=str(response), media_type="application/xml")


@app.api_route("/callback", methods=["POST"])
async def callback(
    ConversationSid: str = Form(...),
    Body: str = Form(None),
    Author: str = Form(...),
):
    """
    Called by Twilio when a message is added to the conversation.
    Sends a reply from OpenAI.
    """
    print(f"📥 New message in {ConversationSid} from {Author}: {Body}")

    if Author.startswith("system") and not Body:
        # Initial system message – greet user
        print("👋 Sending initial greeting...")
        greeting = "Hej! Jag är en AI-assistent. Vad kan jag hjälpa dig med?"
        send_message(ConversationSid, greeting)
        return Response(status_code=200)

    if Author == "bot":
        # Don't respond to our own messages
        return Response(status_code=200)

    # Get response from OpenAI
    try:
        chat_completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ASSISTANT_INSTRUCTIONS},
                {"role": "user", "content": Body},
            ]
        )
        reply = chat_completion.choices[0].message.content.strip()
        print(f"🤖 OpenAI says: {reply}")
        send_message(ConversationSid, reply)

    except Exception as e:
        print(f"⚠️ OpenAI error: {e}")
        send_message(ConversationSid, "Förlåt, något gick fel.")

    return Response(status_code=200)


def send_message(conversation_sid: str, body: str):
    """Sends a message to the Twilio conversation."""
    twilio_client.conversations \
        .conversations(conversation_sid) \
        .messages \
        .create(author="bot", body=body)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
