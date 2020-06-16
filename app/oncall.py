from datetime import datetime
import os
import logging
import boto3
import json
from flask import (
        Flask,
        session,
        redirect,
        url_for,
        request
)
from flask_mail import Mail, Message
from dotenv import load_dotenv
from twilio.twiml.voice_response import VoiceResponse, Gather, Record
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from urllib.parse import urlencode
import urllib
import whos_oncall

load_dotenv()
logging.basicConfig(level=logging.DEBUG)
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

app = Flask(__name__)
app.secret_key = b")DFNG'96.xCn]Vfd^!Cy"
app.config.update(
            MAIL_SERVER=whos_oncall.get_current_mail_server(),
            MAIL_PORT=whos_oncall.get_current_mail_port(),
            MAIL_USE_TLS=whos_oncall.get_current_mail_use_tls(),
            MAIL_USERNAME=whos_oncall.get_current_mail_username(),
            MAIL_PASSWORD=whos_oncall.get_current_mail_password(),
            PERMANENT_SESSION_LIFETIME=whos_oncall.get_current_session_lifetime(),
        )
mailer = Mail(app)

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
@app.route('/public')
@app.route('/msgcontrol')
@app.route('/wrongnumber')
def home():
    return "<html><h1>Invalid request</h1></html>"

@app.route("/wrongnumber/sms", methods=['POST'])
def wrongnumber_sms():
    """Helpful entry point for texts sent to voice numbers"""
    incoming_num = request.values.get('From', '')
    dest_num = request.values.get('To', '')
    logging.debug('Text sent to voice-only number %s from %s. Imparting a hint if sender is known to us.', dest_num, incoming_num)
    resp = MessagingResponse()
    friend = None
    friend = whos_oncall.lookup_user_by_phone(incoming_num)
    if friend != None:
        logging.info('Looked up friend identity %s for %s from config, sending a hint that this (%s) is a voice-only number', friend['name'], incoming_num, dest_num)
        resp.message('Hi there, {}. This is a voice-only number. For text commands you want {} instead.'.format(friend['name'], whos_oncall.get_current_from_phone()))
    if friend == None:
        logging.info("Ignoring message to voice-only number %s from unknown number %s", dest_num, incoming_num)
    return str(resp)

@app.route("/wrongnumber/voice", methods=['POST'])
def wrongnumber_voice():
    """Helpful entry point for voice calls to text-only numbers"""
    incoming_num = request.values.get('From', '')
    dest_num = request.values.get('To', '')
    logging.debug('Voice call to text-only number %s from %s.', dest_num, incoming_num)
    resp = VoiceResponse()
    resp.say('This number does not accept calls.', voice='alice')
    resp.hangup()
    return str(resp)

@app.route("/public/answer", methods=['POST'])
def public_answer():
    """Public entry point. Make the caller press 1 specifically to proceed."""
    incoming_num = request.values.get('From', '')
    dest_num = request.values.get('To', '')
    logging.info('Voice call to voice number %s from caller %s.', dest_num, incoming_num)
    resp = VoiceResponse()
    gather = Gather(num_digits=1, action=url_for('public_keypress'), method="POST")
    gather.say("Press 1 to leave a message for the Open N M S on-call engineer.", voice='alice')
    gather.pause(length=10)
    resp.append(gather)
    return str(resp)

@app.route("/public/keypress", methods=['POST'])
def public_keypress():
    """The caller pressed a key. Now record their message, or hang up if wrong key."""
    selected_option = request.form['Digits']
    logging.info('Caller from %s, SID %s pressed %s', str(request.form.get('From')), str(request.form.get('CallSid')), selected_option)
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
    logging.info('Recording callback invoked with RecordingStatus=%s', rec_status)
    resp = VoiceResponse()
    if rec_status == 'completed':
        _deliver_mms(resp, request)
        _deliver_email(resp, request)
        _persist_recording(resp, request)
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

@app.route("/msgcontrol/entry", methods=['POST'])
def msgcontrol_entry():
    incoming_msg = request.values.get('Body', '').lower().strip()
    incoming_num = request.values.get('From', '')
    resp = MessagingResponse()
    friend = None
    if 'user_dict' in session:
        friend = session['user_dict']
        logging.info('Retrieved friend identity from session')
    else:
        friend = whos_oncall.lookup_user_by_phone(incoming_num)
        if friend != None:
            session['user_dict'] = friend
            logging.info('Looked up friend identity from config, stored in session')
    if friend == None:
        logging.info("Ignoring message from unknown number %s", incoming_num)
        return str(resp)
    if 'take' in incoming_msg:
        resp.redirect(url_for('msgcontrol_take'))
    elif 'who' in incoming_msg:
        resp.redirect(url_for('msgcontrol_who'))
    elif 'c' == incoming_msg:
        resp.redirect(url_for('msgcontrol_confirm'))
    elif 'x' == incoming_msg:
        resp.redirect(url_for('msgcontrol_cancel'))
    elif 'halp' in incoming_msg:
        resp.redirect(url_for('msgcontrol_help'))
    else:
        resp.redirect(url_for('msgcontrol_help'))
    return str(resp)

@app.route("/msgcontrol/take", methods=['POST'])
def msgcontrol_take():
    incoming_msg = request.values.get('Body', '').lower().strip()
    incoming_num = request.values.get('From', '')
    resp = MessagingResponse()
    user_dict = session.get('user_dict')
    if user_dict == None:
        logging.info('No user_dict in session. Bailing.')
        return str(resp)
    current_oncall_user = whos_oncall.get_current_oncall_user()
    if user_dict['id'] == current_oncall_user['id']:
        resp.message('You are already on call, {}. Nothing changes.'.format(user_dict['name']))
        return str(resp)
    resp.message(user_dict['name'] + ' to be made on-call engineer, reply C to confirm or X to cancel')
    session['active_flow'] = 'take'
    return str(resp)

@app.route("/msgcontrol/who", methods=['POST'])
def msgcontrol_who():
    incoming_msg = request.values.get('Body', '').lower().strip()
    incoming_num = request.values.get('From', '')
    resp = MessagingResponse()
    user_dict = session.get('user_dict')
    if user_dict == None:
        logging.info('No user_dict in session. Bailing.')
        return str(resp)
    current_oncall_user = whos_oncall.get_current_oncall_user()
    modified_time = str(datetime.fromtimestamp(whos_oncall.get_oncall_config_last_modified_time()))
    modified_user = whos_oncall.get_oncall_config_last_modified_user_id()
    resp.message('Current on-call engineer: {} <{}>.\nLast modified {} by {}.'.format(current_oncall_user['name'], current_oncall_user['phone'], modified_time, modified_user))
    return str(resp)

@app.route("/msgcontrol/help", methods=['POST'])
def msgcontrol_help():
    incoming_msg = request.values.get('Body', '').lower().strip()
    incoming_num = request.values.get('From', '')
    resp = MessagingResponse()
    user_dict = session.get('user_dict')
    if user_dict == None:
        logging.info('No user_dict in session. Bailing.')
        return str(resp)
    resp.message('Hi there, {}. Commands I understand:\n\n TAKE\n WHO\n HALP\n'.format(user_dict['name']))
    return str(resp)

@app.route("/msgcontrol/confirm", methods=['POST'])
def msgcontrol_confirm():
    incoming_msg = request.values.get('Body', '').lower().strip()
    incoming_num = request.values.get('From', '')
    resp = MessagingResponse()
    user_dict = session.get('user_dict')
    if user_dict == None:
        logging.info('No user_dict in session. Bailing.')
        return str(resp)
    if session.get('active_flow') != 'take':
        logging.info('Got what looks like a take-confirmation, but active_flow is {}. Session expired?'.format(session.get('active_flow')))
        resp.message('No session. Issue TAKE again and confirm within {} seconds.'.format(whos_oncall.get_current_session_lifetime()))
        return str(resp)
    if 'c' != incoming_msg:
        logging.info('This URL is for take-confirmation but the message body {} does not fit. Bailing.'.format(incoming_msg))
        return str(resp)
    whos_oncall.set_current_oncall_user(user_dict['id'], user_dict['id'])
    resp.message('Okay, {}, you are now on call. Please leave a message at {} to complete the flow and test delivery.'.format(user_dict['name'], whos_oncall.get_current_pager_phone()))
    session.pop('active_flow', '')
    return str(resp)

@app.route("/msgcontrol/cancel", methods=['POST'])
def msgcontrol_cancel():
    incoming_msg = request.values.get('Body', '').lower().strip()
    incoming_num = request.values.get('From', '')
    resp = MessagingResponse()
    user_dict = session.get('user_dict')
    if user_dict == None:
        logging.info('No user_dict in session. Bailing.')
        return str(resp)
    if session.get('active_flow') != 'take':
        logging.info('Got what looks like a take-cancel, but active_flow is {}. Session expired?'.format(session.get('active_flow')))
        return str(resp)
    if 'x' != incoming_msg:
        logging.info('This URL is for take-cancel but the message body {} does not fit. Bailing.'.format(incoming_msg))
        return str(resp)
    resp.message('Okay, {}, nothing changes: {} remains on call.'.format(user_dict['name'], whos_oncall.get_current_oncall_user()['name']))
    session.pop('active_flow', '')
    return str(resp)

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
                    from_=whos_oncall.get_current_from_phone(),
                    to=whos_oncall.get_current_oncall_user()['phone'],
                    media_url=call_details['rec_url'],
                    status_callback='{}/{}'.format(os.getenv('ONCALL_APP_BASE_URL'), url_for('public_mmsstatuscb'))
                )
    logging.info('Submitted message with SID %s', msg.sid)
    return resp

def _deliver_email(resp, request):
    call_details = _coalesce_call_details(resp, request)
    email = Message(
                "[OnCall] New on-call voicemail",
                sender=whos_oncall.get_current_from_email(),
                recipients=[whos_oncall.get_current_to_email()],
                body='On-Call voicemail ({} sec) received from {} <{}>. Audio: {}'.format(call_details['rec_len'], call_details['caller_name'], call_details['caller_num'], call_details['rec_url'])
            )
    with urllib.request.urlopen(call_details['rec_url']) as rec_rsp:
        email.attach("voicemail.mp3", "audio/mpeg", rec_rsp.read())
    mailer.send(email)
    return resp

def _persist_recording(resp, request):
    call_details = _coalesce_call_details(resp, request)
    instant = datetime.now()
    base_obj_name = 'recordings/{}'.format(instant.strftime('%Y-%m-%d_%H%M%S'))
    s3c = boto3.client('s3')
    with urllib.request.urlopen(call_details['rec_url']) as rec_rsp:
        s3c.put_object(Bucket=os.getenv('BACKING_STORE_S3_BUCKET'), Key=base_obj_name + '.mp3', Body=rec_rsp.read())
        s3c.put_object(Bucket=os.getenv('BACKING_STORE_S3_BUCKET'), Key=base_obj_name + '.json', Body=json.dumps(call_details, sort_keys=True, indent=4))
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

