from twilio.rest import Client
from os import environ

client = Client(environ['TWILIO_ACCOUNT_SID'], environ['TWILIO_AUTH_TOKEN'])

call = client.calls.create(
                        url='http://demo.twilio.com/docs/voice.xml',
                        to=environ['ONMS_DEFAULT_TARGET_NUMBER'],
                        from_=environ['ONMS_DEFAULT_SOURCE_NUMBER']
                    )

print(call.sid)
