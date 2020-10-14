import imp
import os
import requests
import urllib.request, urllib.parse, urllib.error
import json
import dateutil.tz

import sys
sys.path.append("./tools")
import update_dynamodb

from datetime import datetime

EST = dateutil.tz.gettz('US/Eastern')
CURRENT_DATETIME=datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S')

pluginFolder = "./plugins"
mainFile = "__init__"

with open(os.path.join(os.path.dirname(__file__), 'SLACK_TEAM_TOKEN')) as f:
    incoming_token = f.read().strip()

slack_channel = '#general'
slack_response_url = None
query = None


def getAllPlugins():
    plugins = []
    possibleplugins = os.listdir(pluginFolder)
    for i in possibleplugins:
        location = os.path.join(pluginFolder, i)
        if not os.path.isdir(location) or not mainFile + ".py" in os.listdir(location):
            continue
        info = imp.find_module(mainFile, [location])
        plugins.append({"name": i, "info": info})
    return plugins


# retrieve the incoming webhook
def get_incoming_webhook():
    config = None
    # load config file
    if os.path.isfile("./aws.config"):
        with open("aws.config") as f:
            config = json.load(f)
    return config['General']["webhook_url"]


# retrieve the incoming webhook
def get_dynamodb_table_name():
    config = None
    # load config file
    if os.path.isfile("./aws.config"):
        with open("aws.config") as f:
            config = json.load(f)
    return config['General']["dynamodb_table_name"]

def loadPlugin(pluginName):
    return imp.load_source(pluginName, os.path.join(pluginFolder, pluginName, mainFile + ".py"))


def _formparams_to_dict(s1):
    """ Converts the incoming formparams from Slack into a dictionary. Ex: 'text=votebot+ping' """
    retval = {}
    for val in s1.split('&'):
        k, v = val.split('=')
        retval[k] = v
    return retval


def lambda_handler(event, context):

    print(("Received event: " + json.dumps(event, indent=2)))
    if 'Records' in event:
        alert = event['Records'][0]['Sns']['Message']
        event['formparams'] = str(alert[len("{'formparams': '"):-2])
    # Lambda entry point
    param_map = _formparams_to_dict(event['formparams'])
    query_id = param_map['text']
    text = param_map['text'].split('+')
    global query
    query = urllib.parse.unquote(" ".join(text))
    global slack_channel
    slack_channel = param_map['channel_id']
    retval = None

    global slack_response_url
    slack_response_url = param_map['response_url']
    slack_response_url = urllib.parse.unquote(slack_response_url)
    d_table_name = get_dynamodb_table_name()
    print(("LOG: The request came from: " + slack_channel))
    print(("LOG: The request is: " + str(text)))
    print(("LOG: The requesting user is: " + param_map['user_name']))
    get_latest = False
    date_time_data = ""

    # extract send to slack channel from args
    sendto_data = None
    if "sendto" in text:
        sendto_data = [_f for _f in text[text.index("sendto") + 1:] if _f]
        text = text[:text.index("sendto")]

    if "latest" in text:
        get_latest = True
        text = text[:text.index("latest")]

    if param_map["u'token"] != incoming_token:  # Check for a valid Slack token
        retval = 'invalid incoming Slack token'

    elif text[0] == 'help':
        if len(text) > 1:
            try:
                plugin = loadPlugin(text[1])
                retval = plugin.information()
            except Exception as e:
                retval = "I'm afraid I did not understand that command. Use 'jarvis help' for available commands."
                print(('Error: ' + format(str(e))))
        else:
            plugins = ""
            for aPlugin in getAllPlugins():
                plugins = plugins + "\n" + aPlugin["name"] + ": " + loadPlugin(aPlugin['name']).about()

            retval = 'You can use the following commands: ' + plugins + '.'
    elif get_latest:
        # get latest option
        try:
            plugin = loadPlugin(text[0])
            query_id = "+".join(text)
            retval = plugin.main(text)
            # update the dynamoDB with the new query
            update_dynamodb.update_dynamoDB(d_table_name, query_id, retval,CURRENT_DATETIME)

        except Exception as e:
            retval = "I'm afraid I did not understand that command. Use 'jarvis help' for available commands."
            print(('Error: ' + format(str(e))))
    else:
        try:
            plugin = loadPlugin(text[0])
            query_id = "+".join(text)
            # print(query_id)
            db_result = update_dynamodb.extract_dynamoDB(d_table_name, query_id)
            if db_result:
                retval = db_result[0]
                #retrieve timestamp from dynamodb
                date_time_data = db_result[1]
            else:
                retval = plugin.main(text)
                # update the dynamoDB with the new query
                update_dynamodb.update_dynamoDB(d_table_name, query_id, retval,CURRENT_DATETIME)
        except Exception as e:
            retval = "This query not in Database. Try the command again with 'latest' at end . Use 'jarvis help' for available commands."
            print(('Error: ' + format(str(e))))

    print("******************return value of slack payload*********************")
    print(retval)
    print("*********************************************************************")

    # if sendto: is in args then send jarvis message to slack channel in args
    if sendto_data:
        send_to_slack(retval, sendto_data[0], param_map['user_name'],date_time_data)
    else:
        post_to_slack(retval, date_time_data)


# function to send processing request message
def send_message_to_slack(val):
    try:
        payload = {
            "text": val,
            "response_type": "ephemeral"
        }
        r = requests.post(slack_response_url, json=payload)
    except Exception as e:
        print(("ephemeral_message_request error " + str(e)))


def post_to_slack(val, date_time_data=""):
    date_data = ""
    if date_time_data:
        date_data = "\nRetrieved on: "+date_time_data

    if isinstance(val, str):
        payload = {
        "text": query + date_data + "\n" + val,
        "response_type": "ephemeral"
        }
        r = requests.post(slack_response_url, json=payload)
    else:
        payload = {
        "text": query + date_data,
        "attachments": val,
        "response_type": "ephemeral"
        }
        r = requests.post(slack_response_url, json=payload)


def send_to_slack(val, sendto_slack_channel, sender_address, date_time_data=""):
    date_data = ""
    if date_time_data:
        date_data = "\nRetrieved on: " + date_time_data
    # this gives easy access to incoming webhook
    sendto_webhook = get_incoming_webhook()

    sendto_slack_channel = urllib.parse.unquote(sendto_slack_channel)

    # information stating requester of data
    sender_title = urllib.parse.unquote(sender_address) + " has requested this information from J.A.R.V.I.S.\n"

    if isinstance(val, str):
        try:
            payload = {
                "text": query + date_data + "\n" + val,
                "response_type": "ephemeral"
            }
            r = requests.post(slack_response_url, json=payload)
        except Exception as e:
            print(("ephemeral_message_request error "+str(e)))

        try:
            # send to another slack channel
            if sendto_slack_channel:
                # creating json payload
                payload = {
                    'text': sender_title + '_' + query + '_'+ date_data + "\n" + val,
                    'as_user': False,
                    "channel": sendto_slack_channel,
                    'mrkdwn': 'true'
                }
                incoming_message_request = requests.post(sendto_webhook, json=payload)

                # if the slack message was not posted then send a message to sender
                if incoming_message_request.status_code != 200:
                    print((
                        'In send_to_slack ephemeral Slack returned status code %s, the response text is %s' % (
                            incoming_message_request.status_code, incoming_message_request.text)
                    ))

                    send_message_to_slack('Unable to execute sendto command, retry with a valid  user or channel')

        except Exception as e:
            print(("sendto_message_request error " + str(e)))
    else:
        try:
            payload = {
                "text": query + date_data,
                "attachments": val,
                "response_type": "ephemeral"
            }
            ephemeral_message_request = requests.post(slack_response_url, json=payload)
        except Exception as e:
            print(("ephemeral_message_request error "+str(e)))

        # after sending a message to your current channel,
        # then send another to the desired slack channel

        # creating json payload
        try:
            if sendto_slack_channel:
                payload = {
                    'text': sender_title +'_' + query + '_' + date_data,
                    'as_user': False,
                    "channel": sendto_slack_channel,
                    "attachments": val,
                    'mrkdwn': 'true'
                }

                incoming_message_request = requests.post(sendto_webhook, json=payload)

                # if the slack message was not posted then send a message to sender
                if incoming_message_request.status_code != 200:
                    print((
                        'In send_to_slack ephemeral Slack returned status code %s, the response text is %s' % (
                            incoming_message_request.status_code, incoming_message_request.text)
                    ))

                    send_message_to_slack('Unable to execute sendto command, retry with a valid user or channel')

        except Exception as e:
            print(("sendto_message_request error "+str(e)))


if __name__ == '__main__':
    context = None
    with open(os.path.join(os.path.dirname(__file__), 'test_event.json')) as f:
        event = json.loads(f.read().strip())
    lambda_handler(event, context)
