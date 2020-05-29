from flask import (
        Flask,
        url_for
)
from twilio.twiml.voice_response import VoiceResponse, Gather, Record

app = Flask(__name__)

@app.route('/')
@app.route('/public')
def home():
    return "<html><h1>Nothing to see here</h1></html>"

@app.route("/public/answer", methods=['GET', 'POST'])
def public_answer():
    """Public entry point. Make the caller press 1 specifically to proceed."""
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
    option_actions = {'1': _record_message,
                      '2': _disconnect_call}
    if option_actions.has_key(selected_option):
        resp = VoiceResponse()
        option_actions[selected_option](resp)
        return str(response)
    return _disconnect_call()

def _record_message(resp):
    resp.record(max_length=300, recording_status_callback=url_for(public_sendmms), recording_status_callback_event='completed absent', recording_status_callback_method='POST')
    return resp

def _disconnect_call(resp):
    resp.say("Goodbye", voice='alice')
    resp.hangup()
    return resp

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')

