import logging
import os
from flask import (
        Flask,
        url_for,
        request
)
from flask_mail import Mail, Message
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
from twilio.rest import Client
from urllib.parse import urlencode
import urllib

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

app = Flask(__name__)

app.config.update(
            DEBUG=True,
            MAIL_SERVER='aspmx.l.google.com',
            MAIL_PORT=25,
            MAIL_USE_TLS=True
        )

mailer = Mail(app)

@app.route('/')
@app.route('/public')
def home():
    return "<html><h1>Nothing to see here</h1></html>"

@app.route("/public/answer", methods=['POST'])
def public_answer():
    """Public entry point. Make the caller press 1 specifically to proceed."""
    logging.debug('Yo, I got a call here from %s, SID %s', str(request.form.get('From')), str(request.form.get('CallSid')))
    resp = VoiceResponse()
    with resp.gather(
            num_digits=1, action=url_for('public_keypress'), method="POST"
    ) as g:
        g.say(message="Press 1 to leave a message for the Open N M S on-call engineer.", voice='alice')
    return str(resp)

@app.route("/public/keypress", methods=['POST'])
def public_keypress():
    """The caller pressed a key. Now record their message, or hang up if wrong key."""
    selected_option = request.form['Digits']
    logging.debug('Caller from %s, SID %s pressed %s', str(request.form.get('From')), str(request.form.get('CallSid')), selected_option)
    resp = VoiceResponse()
    if selected_option == '1':
        _record_message(resp, request)
    else:
        _disconnect_call(resp, request)
    return str(resp)

@app.route("/public/afterrec", methods=['POST'])
def public_afterrec():
    """The caller left a message and stayed on the line. Provide feedback."""
    resp = VoiceResponse()
    rec_len = request.form['RecordingDuration']
    resp.say("I'm going to deliver your " + rec_len + " second message to the on-call engineer now. You will receive a callback as soon as possible.")
    resp.hangup()
    return str(resp)

@app.route("/public/recordingcb", methods=['POST'])
def public_recordingcb():
    """Recording status callback function for the public flow"""
    rec_status = request.form['RecordingStatus']
    resp = VoiceResponse()
    if rec_status == 'completed':
        _deliver_mms(resp, request)
        _deliver_email(resp, request)
    elif rec_status == 'failed':
        _record_failed(resp, request)
    else:
        _record_failed(resp, request)
    return str(resp)

@app.route("/public/mmsstatuscb", methods=['POST'])
def public_mmsstatuscb():
    """MMS delivery status callback function for the public flow"""
    message_sid = request.values.get('MessageSid')
    message_status = request.values.get('MessageStatus')
    logging.info('Message status: %s / %s', message_sid, message_status)
    logging.debug('Message status DUMP: %s', request.values)
    if (message_status == 'failed' or message_status == 'undelivered'):
        logging.error('Message with SID %s has unacceptable status: %s', message_sid, message_status)
    return ('', 204)

def _record_message(resp, request):
    relay_vars = {'OnmsOrigFrom': request.form['From'],
                  'OnmsOrigFromCity': request.form['FromCity'],
                  'OnmsOrigFromState': request.form['FromState'],
                  'OnmsOrigCallerName': request.form['CallerName'],
                  'OnmsOrigCallSid': request.form['CallSid']}
    relay_query = urlencode(relay_vars)
    resp.record(action=url_for('public_afterrec'), max_length=300, recording_status_callback=url_for('public_recordingcb') + '?' + relay_query, recording_status_callback_event='completed absent', recording_status_callback_method='POST')
    return resp

def _coalesce_call_details(resp, request):
    details = dict()
    details['orig_call_sid'] = str(request.args.get('OnmsOrigCallSid'))
    details['caller_num'] = str(request.args.get('OnmsOrigFrom'))
    if 'OnmsOrigCallerName' in request.args:
        details['caller_name'] = str(request.args.get('OnmsOrigCallerName'))
    elif 'OnmsOrigFromCity' in request.args:
        details['caller_name'] = str(request.args.get('OnmsOrigFromCity')) + " " + str(request.args.get('OnmsOrigFromState'))
    else:
        details['caller_name'] = 'Unknown Caller'
    details['rec_len'] = request.form['RecordingDuration']
    details['rec_url'] = '{}.mp3'.format(request.form['RecordingUrl'])
    return details

def _deliver_mms(resp, request):
    call_details = _coalesce_call_details(resp, request)
    logging.info('Call from %s, SID %s: Sending MMS of %s-second message from %s <%s> with MediaUrl=%s', call_details['caller_num'], call_details['orig_call_sid'], call_details['rec_len'], call_details['caller_name'], call_details['caller_num'], call_details['rec_url'])
    msg = client.messages.create(
                    body='On-Call voicemail ({} sec) received from {} <{}>'.format(call_details['rec_len'], call_details['caller_name'], call_details['caller_num']),
                    from_=os.getenv("ONMS_DEFAULT_SOURCE_NUMBER"),
                    to=os.getenv("ONMS_DEFAULT_TARGET_NUMBER"),
                    media_url=call_details['rec_url'],
                    status_callback='{}/{}'.format(os.getenv('ONCALL_APP_BASE_URL'), url_for('public_mmsstatuscb'))
                )
    logging.info('Submitted message with SID %s', msg.sid)
    return resp

def _deliver_email(resp, request):
    call_details = _coalesce_call_details(resp, request)
    email = Message(
                "[OnCall] New on-call voicemail",
                sender="oncall-dev@opennms.com",
                recipients=["jeffg@opennms.com"],
                body='On-Call voicemail ({} sec) received from {} <{}>. Audio: {}'.format(call_details['rec_len'], call_details['caller_name'], call_details['caller_num'], call_details['rec_url'])
            )
    with urllib.request.urlopen(call_details['rec_url']) as rec_rsp:
        email.attach("voicemail.mp3", "audio/mpeg", rec_rsp.read())
    mailer.send(email)
    return resp

def _record_failed(resp, request):
    resp.say("Sorry, your message didn't record successfully. Let's try again.")
    resp.redirect(url_for(public_answer))

def _disconnect_call(resp, request):
    resp.say("Goodbye", voice='alice')
    resp.hangup()
    return resp

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')

