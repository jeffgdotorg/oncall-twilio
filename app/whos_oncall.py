import logging
import os
import time
from dotenv import load_dotenv
import boto3
import json
import re

load_dotenv()
logging.basicConfig(level=logging.INFO)

def get_current_oncall_user():
    config = _get_oncall_config()
    return config['current_config']['oncall_user']

def set_current_oncall_user(user_id, actor_id):
    config = _get_oncall_config()
    assert user_id in config['available_users']['users']
    config['current_config']['oncall_user'] = config['available_users']['users'][user_id]
    _set_oncall_config(config, actor_id)

def get_current_pager_phone():
    config = _get_oncall_config()
    return config['current_config']['pager_phone']

def get_current_from_phone():
    config = _get_oncall_config()
    return config['current_config']['from_phone']

def get_current_from_email():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['from_email']

def get_current_to_email():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['to_email']

def get_current_mail_password():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['mail_password']

def get_current_mail_port():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['mail_port']

def get_current_mail_server():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['mail_server']

def get_current_mail_use_tls():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['mail_use_tls']

def get_current_mail_username():
    config = _get_oncall_config()
    return config['current_config']['mail_settings']['mail_username']

def get_current_session_lifetime():
    config = _get_oncall_config()
    return config['current_config']['session_lifetime']

def get_available_oncall_users():
    config = _get_oncall_config()
    return config['available_users']['users']

def get_oncall_config_last_modified_time():
    config = _get_oncall_config()
    return config['current_config']['last_modified_time']

def get_oncall_config_last_modified_user_id():
    config = _get_oncall_config()
    return config['current_config']['last_modified_user_id']

def lookup_user_by_phone(phonenum):
    config = _get_oncall_config()
    for user_id, user_dict in config['available_users']['users'].items():
        if phonenum == user_dict['phone']:
            return user_dict
    return None

def _validate_oncall_config(config_dict):
    assert 'current_config' in config_dict, 'Top-level current_config not present'
    assert 'oncall_user' in config_dict['current_config'], 'current_config.oncall_user not present'
    assert _validate_user(config_dict['current_config']['oncall_user']), 'current_config.oncall_user fails validation'
    assert _validate_top_contact_items(config_dict['current_config']), 'current_config contact items fail validation'
    assert 'last_modified_time' in config_dict['current_config'], 'current_config.last_modified_time not present'
    assert 'last_modified_user_id' in config_dict['current_config'], 'current_config.last_modified_user_id not present'
    assert 'available_users' in config_dict, 'Top-level available_users not present'
    assert 'users' in config_dict['available_users'], 'available_users.users not present'
    for user_id, user_dict in config_dict['available_users']['users'].items():
        assert _validate_user(user_dict), 'available_users item ' + user_id + ' failed validation'
    assert _validate_available_users_unique(config_dict['available_users']), 'available_users failed uniqueness check'
    assert _validate_mail_settings(config_dict['current_config']['mail_settings']), 'current_config.mail_settings failed validation'
    assert 'session_lifetime' in config_dict['current_config'], 'current_config.session_lifetime not present'
    return True

def _validate_top_contact_items(current_config):
    assert 'pager_phone' in current_config, 'current_config lacks pager_phone'
    assert re.fullmatch(r"^\+1[2-9][0-9]{2}[2-9][0-9]{6}$", current_config['pager_phone']), 'current_config pager_phone ' + current_config['pager_phone'] + ' failed validation'
    assert 'from_phone' in current_config, 'current_config lacks from_phone'
    assert re.fullmatch(r"^\+1[2-9][0-9]{2}[2-9][0-9]{6}$", current_config['from_phone']), 'current_config from_phone ' + current_config['from_phone'] + ' failed validation'
    return True

def _validate_available_users_unique(available_users_dict):
    phone_dedup = dict()
    name_dedup = dict()
    for user_id, user_dict in available_users_dict['users'].items():
        assert user_dict['id'] == user_id, 'Available user record outer ID ' + user_id + ' mismatched with inner id ' + user_dict['id']
        assert user_dict['phone'] not in phone_dedup, 'Phone ' + user_dict['phone'] + ' is not unique among available users'
        phone_dedup[user_dict['phone']] = user_dict['phone']
        assert user_dict['name'] not in name_dedup, 'Name ' + user_dict['name'] + ' is not unique among available users'.format(user_dict['phone'])
        name_dedup[user_dict['name']] = user_dict['name']
    return True

def _validate_user(user_dict):
    assert 'id' in user_dict, 'User id not present'
    assert 'name' in user_dict, 'User name not present'
    assert 'phone' in user_dict, 'User phone not present'
    assert re.fullmatch(r"^\+1[2-9][0-9]{2}[2-9][0-9]{6}$", user_dict['phone']), 'User phone ' + user_dict['phone'] + ' failed validation'
    return True

def _validate_mail_settings(mail_settings):
    assert 'from_email' in mail_settings, 'current_config.mail_settings lacks from_email'
    assert re.fullmatch(r"\S+@\S+\.\S+", mail_settings['from_email']), 'current_config.mail_settings from_email ' + mail_settings['from_email'] + ' failed validation'
    assert 'mail_password' in mail_settings, 'current_config.mail_settings lacks mail_password'
    assert 'mail_port' in mail_settings, 'current_config.mail_settings lacks mail_port'
    assert 'mail_server' in mail_settings, 'current_config.mail_settings lacks mail_server'
    assert 'mail_use_tls' in mail_settings, 'current_config.mail_settings lacks mail_use_tls'
    assert 'mail_username' in mail_settings, 'current_config.mail_settings lacks mail_user'
    assert 'to_email' in mail_settings, 'current_config.mail_settings lacks to_email'
    assert re.fullmatch(r"\S+@\S+\.\S+", mail_settings['to_email']), 'current_config.mail_settings to_email ' + mail_settings['to_email'] + ' failed validation'
    return True

def _get_oncall_config():
    s3c = boto3.client('s3')
    config_obj = s3c.get_object(Bucket=os.getenv('BACKING_STORE_S3_BUCKET'), Key=os.getenv('BACKING_STORE_S3_KEY'))
    config_dict = json.loads(config_obj['Body'].read())
    if _validate_oncall_config(config_dict):
        return config_dict
    else:
        return {}

def _set_oncall_config(config_dict, actor_id):
    config_dict['current_config']['last_modified_time'] = int(time.time())
    config_dict['current_config']['last_modified_user_id'] = actor_id
    assert _validate_oncall_config(config_dict)
    s3c = boto3.client('s3')
    s3c.put_object(Bucket=os.getenv('BACKING_STORE_S3_BUCKET'), Key=os.getenv('BACKING_STORE_S3_KEY'), Body=json.dumps(config_dict, sort_keys=True, indent=4))
    return config_dict
