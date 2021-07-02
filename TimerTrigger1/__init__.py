import os
import json
import datetime
import logging
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
from slack import WebClient
from slack.errors import SlackApiError
import azure.functions as func
from azure.appconfiguration import AzureAppConfigurationClient, ConfigurationSetting
from azure.core.exceptions import ResourceNotFoundError
from enum import Enum

app_config_connection_string = os.getenv('AZURE_APP_CONFIG_CONNECTION_STRING')

slack_token = os.getenv("SLACK_TOKEN")
slack_channel_id = os.getenv("SLACK_CHANNEL_ID")
client = WebClient(token=slack_token)

#logging.basicConfig(level=logging.DEBUG)

class Targets(Enum):
    SeeedKK = ('https://www.seeed.co.jp/', 'UrlMonitor:Web.SeeedKK:Status')
    #Google = ('https://www.google.co.jp/', 'UrlMonitor:Web.Google:Status')

    def __init__(self, url, key):
        self.url = url
        self.key = key

def update_status_on_appconf(target, value):
    logging.info('  ==> statusUpdate: ' + value + ' (' + target.key + ')')
    app_config_client = AzureAppConfigurationClient.from_connection_string(app_config_connection_string)
    config_setting = ConfigurationSetting(key=target.key, value=value)
    target_status = app_config_client.set_configuration_setting(config_setting)
    return target_status

def previous_status_on_appconf(target):
    app_config_client = AzureAppConfigurationClient.from_connection_string(app_config_connection_string)
    try:
        target_status = app_config_client.get_configuration_setting(key=target.key)
    except ResourceNotFoundError:
        target_status = update_status_on_appconf(target, 'Unknown')
    return target_status

def send_notification(message):
    logging.info('  ==> postMessage: ' + message)
    for i in range(3):
        try:
            response = client.chat_postMessage(channel=slack_channel_id, text=message)
        except SlackApiError as e:
            logging.error('failed to chat_postMessage: %s', e.response['error'])
        else:
            break

def main(mytimer: func.TimerRequest) -> None:
    jst_timestamp = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=9), name='JST')).isoformat()

    if mytimer.past_due:
        logging.info('The timer is past due!')

    logging.info('Python timer trigger function ran at %s', jst_timestamp)

    session = requests.Session()
    retries = Retry(total=3,
                    backoff_factor=1,
                    status_forcelist=[500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))

    for target in Targets:
        error_message = ''
        try:
            status_code = requests.get(target.url, timeout=(10.0, 30.0)).status_code
        except requests.exceptions.ReadTimeout:
            error_message = 'Timeout'
        except requests.exceptions.ConnectionError:
            error_message = 'Connection error'
        else:
            if status_code == 200:
                pass
            else:
                error_message = "Status Code " + str(status_code)

        status = previous_status_on_appconf(target)
        if not error_message:
            logging.info('[ OK]: %s', target.url)
            if not 'Running' in status.value:
                update_status_on_appconf(target, 'Running')
                message = '- ' + target.url + ' is running normally.'
                send_notification(message)
        else:
            logging.info('[ERR]: %s (%s)', target.url, error_message)
            if 'Running' in status.value:
                update_status_on_appconf(target, 'Stopping')
                message = '- An error has been detected on ' + target.url + '.'
                send_notification(message)
