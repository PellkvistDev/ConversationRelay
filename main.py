from fastapi import FastAPI, Request
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect
import openai
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")  # format: ACCOUNT_SID:AUTH_TOKEN

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

@app.post("/voice")
async def voice(request: Request):
    """Handles initial voice call"""
    response = VoiceResponse()
    connect = Connect()
    connect.conversation(
        service_instance_sid=os.getenv("CONVERSATION_SERVICE_SID"),
        speech_configuration_sid=os.getenv("SPEECH_CONFIGURATION_SID")
    )
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@app.post("/callback")
async def callback(request: Request):
    """Handles ConversationRelay speech callback"""
    form = await request.form()
    speech_result = form.get("SpeechResult")
    convo_sid = form.get("ConversationSid")
    participant_sid = form.get("ParticipantSid")

    if speech_result:
        print("User said:", speech_result)

        # Send to OpenAI
        chat_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": speech_result}],
        )
        message = chat_response.choices[0].message.content
        print("OpenAI response:", message)

        # Send message to Twilio Conversation
        url = f"https://conversations.twilio.com/v1/Conversations/{convo_sid}/Participants/{participant_sid}/Messages"
        auth = httpx.BasicAuth(*TWILIO_AUTH.split(":", 1))
        await httpx.post(url, data={"Body": message}, auth=auth)

    return {"status": "ok"}
