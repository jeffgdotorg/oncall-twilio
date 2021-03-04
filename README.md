oncall-twilio
=============
This project implements a simple on-call pager in Python / Flask using Twilio's programmable voice and programmable messaging APIs.
It is suitable for use by small teams with modest needs, and is not meant to compete with the many fine services available in the market which provide a superset of its capabilities.

At bottom, it is really just a [TwiML](https://www.twilio.com/docs/voice/twiml) app.
Its operational configuration, including who is currently on-call, who is allowed to become on-call, and a few other items, lives in a JSON file stored in an S3 bucket; recorded messages and a basic audit log are also saved in S3.
Team members listed in that JSON config may operate the system remotely by sending SMS messages containing key words including `WHO`, `TAKE`, and `HALP`.
SMS messages from non-members are ignored.

Requirements
============
You will need the following:

# Several Python modules installed, preferably inside a virtual environment; the required modules are listed in `requirements.txt`
# A [Twilio](https://www.twilio.com) account with at least one phone number capable of handling voice, SMS, and MMS
# A place to host the app; any platform capable of running Python and Flask should do, but it has been tested on Linux (CentOS 8).
# An [AWS](https://aws.amazon.com/getting-started/) account with permission to configure S3 buckets
# An SMTP relay, for delivering copies of recorded messages via e-mail as a backup mechanism

Operational Configuration
=========================
The operational configuration file (JSON) looks as follows:

```json
{
    "available_users": {
        "users": {
            "alice": {
                "id": "alice",
                "name": "Alice McAlister",
                "phone": "+19195551001"
            },
            "bob": {
                "id": "bob",
                "name": "Bob Roberts",
                "phone": "+19195551002"
            }
        }
    },
    "current_config": {
        "from_phone": "+19195559876",
        "last_modified_time": 1611602242,
        "last_modified_user_id": "alice",
        "mail_settings": {
            "from_email": "oncall@example.com",
            "mail_password": "ktmyastgLYrB5bkpNdsx",
            "mail_port": 25,
            "mail_server": "smtp.example.com",
            "mail_use_tls": true,
            "mail_username": "oncall_pager_smtp",
            "to_email": "sre@example.com"
        },
        "oncall_user": {
            "id": "alice",
            "name": "Alice McAlister",
            "phone": "+9195551001"
        },
        "pager_phone": "+18002255288",
        "session_lifetime": 300
    }
}
```

The on-call system expects to interact with the team (Alice and Bob) via the phone number in the `current_config.from_phone` property.
The system expects customers to leave messages at the number in the `current_config.pager_phone` property.
These two numbers could be one and the same, but it is expected that they differ.

App Configuration
=================
Configuration required to get the app up and running lives in the filesystem of the hosting OS, alongside the app files.

The user under whose account the app will run needs to have a `~/.aws/credentials` file which sets at least `aws_access_key_id`, `aws_secret_access_key`, and `region` to enable access to S3.
If you host the app on EC2 or another AWS compute service, it may be possible to configure AWS credentials by other means.

An example of setting the S3 bucket and key which holds the operational configuration are found in `backingstore.env.example`.
An example base URL at which the running TwiML application can be reached is in `server_meta.env.example`.
Examples of the API key and auth token for interacting with the Twilio APIs live in `twilio.env.example`.
You should concatenate these three files together into a compound file named `.env` inside the `app` directory, and edit to provide your own values for the several variables.

Running It
==========
Run the app under a production-suited WSGI server such as [Gunicorn](https://gunicorn.org) and secure it with HTTPS; NGinX and [LetsEncrypt](https://letsencrypt.org) provide an easy, no-cost way to do this.
Set up the server to run under Systemd; Dockerizing it is on my to-do list.

Configuring Twilio
==================
In the Twilio console, configure the number which you set as your `current_config.pager_phone` so that its voice entry-point URL is `BASE_URL/public/answer`.
Configure the number set as your `current_config.from_phone` so that its SMS entry-point URL is `BASE_URL/msgcontrol/entry`.
If your `pager_phone` and `from_phone` numbers differ, you may want to set the `from_phone` number's voice entry-point URL to `BASE_URL/wrongnumber/sms` and the `pager_phone` number's SMS entry-point URL to `BASE_URL/wrongnumber/sms`.
This way if a team member accidentally texts the pager call-in number, they'll be reminded to use the other number instead, and anybody dialing the number that the team is meant to be texting will get a short message before the call is ended.

Controlling via SMS
===================
Any team member can control the system by SMSing the number configured as `current_config.from_phone` with the following commands:

* Learn who is currently on-call: `WHO`
* Become on-call: `TAKE`, followed by completion of a confirmation exchange within the configured timeout window
* Get a summary of supported commands: `HALP` (`HELP` is reserved and captured by Twilio in most cases)

The effect of the `TAKE` action is reflected in the operational config, a new version of which is written to the S3 bucket.

Changing the Configuration
==========================
At the moment, the only way to add new team members, remove departed ones, or otherwise change the operational configuration is to create and upload a new version of the config to the appropriate S3 bucket.
Naturally you will have a dev and a prod environment for this service, and will test your changes in dev :)

Have fun!
