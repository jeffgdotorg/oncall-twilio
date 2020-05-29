import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

call = client.calls.create(
                        url='http://demo.twilio.com/docs/voice.xml',
                        to=os.getenv("ONMS_DEFAULT_TARGET_NUMBER"),
                        from_=os.getenv("ONMS_DEFAULT_SOURCE_NUMBER")
                    )

print(call.sid)
