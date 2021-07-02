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

slack_token = os.getenv("SLACK_TOKEN")
slack_channel_id = os.getenv("SLACK_CHANNEL_ID")
client = WebClient(token=slack_token)

targets = ['https://www.seeed.co.jp/']
in_errors = {}

#logging.basicConfig(level=logging.DEBUG)

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

    for url in targets:
        error_message = ''
        try:
            status_code = requests.get(url, timeout=(10.0, 30.0)).status_code
        except requests.exceptions.ReadTimeout:
            error_message = 'Timeout'
        except requests.exceptions.ConnectionError:
            error_message = 'Connection error'
        else:
            if status_code == 200:
                pass
            else:
                error_message = "Status Code " + str(status_code)

        in_error = in_errors.get(url, False)
        if not error_message:
            logging.info('[ OK]: %s', url)
            if in_error == True:
                in_errors[url] = False
                message = '- ' + url + ' is running normally.'
                send_notification(message)
        else:
            logging.info('[ERR]: %s (%s)', url, error_message)
            if in_error == False:
                in_errors[url] = True
                message = '- An error has been detected on ' + url + '.'
                send_notification(message)
