import logging
import os
from dotenv import load_dotenv
import boto3
import json
import re

load_dotenv()
logging.basicConfig(level=logging.INFO)

def get_current_oncall_user():
    config = _get_oncall_config()
    return config['current_config']['user']

def set_current_oncall_user(user_id):
    config = _get_oncall_config()
    assert user_id in config['available_users']['users']
    config['current_config']['user'] = config['available_users']['users'][user_id]
    _set_oncall_config(config)

def get_current_pager_phone():
    config = _get_oncall_config()
    return config['current_config']['pager_phone']

def get_current_from_phone():
    config = _get_oncall_config()
    return config['current_config']['from_phone']

def get_current_from_email():
    config = _get_oncall_config()
    return config['current_config']['from_email']

def get_current_to_email():
    config = _get_oncall_config()
    return config['current_config']['to_email']

def get_available_oncall_users():
    config = _get_oncall_config()
    return config['available_users']['users']

def lookup_user_by_phone(phonenum):
    config = _get_oncall_config()
    for user_id, user_dict in config['available_users']['users'].items():
        if phonenum == user_dict['phone']:
            return user_dict
    return None

def _validate_oncall_config(config_dict):
    assert 'current_config' in config_dict, 'Top-level current_config not present'
    assert 'user' in config_dict['current_config'], 'current_config.user not present'
    assert _validate_user(config_dict['current_config']['user']), 'current_config.user fails validation'
    assert _validate_top_contact_items(config_dict['current_config']), 'current_config contact items fail validation'
    assert 'modified' in config_dict['current_config'], 'current_config.modified not present'
    assert 'available_users' in config_dict, 'Top-level available_users not present'
    assert 'users' in config_dict['available_users'], 'available_users.users not present'
    for user_id, user_dict in config_dict['available_users']['users'].items():
        assert _validate_user(user_dict), 'available_users item ' + user_id + ' failed validation'
    assert _validate_available_users_unique(config_dict['available_users']), 'available_users failed uniqueness check'
    return True

def _validate_top_contact_items(current_config):
    assert 'pager_phone' in current_config, 'current_config lacks pager_phone'
    assert re.fullmatch(r"^\+1[2-9][0-9]{2}[2-9][0-9]{6}$", current_config['pager_phone']), 'current_config pager_phone ' + current_config['pager_phone'] + ' failed validation'
    assert 'from_phone' in current_config, 'current_config lacks from_phone'
    assert re.fullmatch(r"^\+1[2-9][0-9]{2}[2-9][0-9]{6}$", current_config['from_phone']), 'current_config from_phone ' + current_config['from_phone'] + ' failed validation'
    assert 'from_email' in current_config, 'current_config lacks from_email'
    assert re.fullmatch(r"\S+@\S+\.\S+", current_config['from_email']), 'current_config from_email ' + current_config['from_email'] + ' failed validation'
    assert 'to_email' in current_config, 'current_config lacks to_email'
    assert re.fullmatch(r"\S+@\S+\.\S+", current_config['to_email']), 'current_config to_email ' + current_config['to_email'] + ' failed validation'
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

def _get_oncall_config():
    s3c = boto3.client('s3')
    config_obj = s3c.get_object(Bucket=os.getenv('BACKING_STORE_S3_BUCKET'), Key=os.getenv('BACKING_STORE_S3_KEY'))
    config_dict = json.loads(config_obj['Body'].read())
    if _validate_oncall_config(config_dict):
        return config_dict
    else:
        return {}

def _set_oncall_config(config_dict):
    assert _validate_oncall_config(config_dict)
    s3c = boto3.client('s3')
    s3c.put_object(Bucket=os.getenv('BACKING_STORE_S3_BUCKET'), Key=os.getenv('BACKING_STORE_S3_KEY'), Body=json.dumps(config_dict, sort_keys=True, indent=4))
    return config_dict
