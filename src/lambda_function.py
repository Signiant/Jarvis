import imp
import os, sys
from collections import defaultdict
import requests
import urllib
import logging
import json
import datetime
import pprint
import json


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

#retrieve the incoming webhook
def get_incoming_webhook():
    config = None
    # load config file
    if os.path.isfile("./aws.config"):
        with open("aws.config") as f:
            config = json.load(f)
    return config['General']["webhook_url"]

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
    if event.haskey('Records'):
        alert = event['Records'][0]['Sns']['Message']
        event = json.loads(alert)
    # Lambda entry point
    param_map = _formparams_to_dict(event['formparams'])
    text = param_map['text'].split('+')
    global query
    query = urllib.unquote(" ".join(text))
    global slack_channel
    slack_channel = param_map['channel_id']
    retval = None

    global slack_response_url
    slack_response_url = param_map['response_url']
    slack_response_url = urllib.unquote(slack_response_url)

    print "LOG: The request came from: " + slack_channel
    print "LOG: The request is: " + str(text)
    print "LOG: The requesting user is: " + param_map['user_name']

    #extract send to slack channel from args
    sendto_data = None
    if "sendto" in text:
        sendto_data = filter(None, text[text.index("sendto") + 1:])
        text = text[:text.index("sendto")]

    if param_map['token'] != incoming_token:  # Check for a valid Slack token
        retval = 'invalid incoming Slack token'

    elif text[0] == 'help':
        if len(text) > 1:
            try:
                plugin = loadPlugin(text[1])
                retval = plugin.information()
            except Exception as e:
                retval = "I'm afraid I did not understand that command. Use 'jarvis help' for available commands."
                print 'Error: ' + format(str(e))
        else:
            plugins = ""
            for aPlugin in getAllPlugins():
                plugins = plugins + "\n" + aPlugin["name"] + ": " + loadPlugin(aPlugin['name']).about()

            retval = 'You can use the following commands: ' + plugins + '.'
    else:
        try:

            #The boto calls in the compare command cause long wait times, so this processing
            # message is sent to notify the requester
            send_message_to_slack("I'm processing your request, please stand by")

            plugin = loadPlugin(text[0])
            retval = plugin.main(text)
        except Exception as e:
            retval = "I'm afraid I did not understand that command. Use 'jarvis help' for available commands."
            print 'Error: ' + format(str(e))


    logging.info("******************return value of slack payload*********************")
    logging.info(retval)
    logging.info("*********************************************************************")

    #if sendto: is in args then send jarvis message to slack channel in args
    if sendto_data:
        send_to_slack(retval, sendto_data[0], param_map['user_name'])
    else:
        post_to_slack(retval)


#function to send processing request message
def send_message_to_slack(val):
    try:
        payload = {
            "text": val,
            "response_type": "ephemeral"
        }
        r = requests.post(slack_response_url, json=payload)
    except Exception as e:
        print "ephemeral_message_request error " + str(e)


def post_to_slack(val):
    if isinstance(val, basestring):
        payload = {
        "text": query + "\n" + val,
        "response_type": "ephemeral"
        }
        r = requests.post(slack_response_url, json=payload)
    else:
        payload = {
        "text": query,
        "attachments": val,
        "response_type": "ephemeral"
        }
        r = requests.post(slack_response_url, json=payload)


def send_to_slack(val, sendto_slack_channel, sender_address):
    # this gives easy access to incoming webhook
    sendto_webhook = get_incoming_webhook()

    sendto_slack_channel = urllib.unquote(sendto_slack_channel)

    #information stating requester of data
    sender_title = urllib.unquote(sender_address) + " has requested this information from J.A.R.V.I.S.\n"

    if isinstance(val, basestring):
        try:
            payload = {
                "text": query + "\n" + val,
                "response_type": "ephemeral"
            }
            r = requests.post(slack_response_url, json=payload)
        except Exception as e:
            print "ephemeral_message_request error "+str(e)

        try:
            #send to another slack channel
            if sendto_slack_channel:
                # creating json payload
                payload = {
                    'text': sender_title + '_' + query + '_'+ "\n" + val,
                    'as_user': False,
                    "channel": sendto_slack_channel,
                    'mrkdwn': 'true'
                }
                incoming_message_request = requests.post(sendto_webhook, json=payload)

                #if the slack message was not posted then send a message to sender
                if incoming_message_request.status_code != 200:
                    print (
                        'In send_to_slack ephemeral Slack returned status code %s, the response text is %s' % (
                            incoming_message_request.status_code, incoming_message_request.text)
                    )


                    send_message_to_slack('Unable to execute sendto command, retry with a valid  user or channel')




        except Exception as e:
            print "sendto_message_request error " + str(e)
    else:
        try:
            payload = {
                "text": query,
                "attachments": val,
                "response_type": "ephemeral"
            }
            ephemeral_message_request = requests.post(slack_response_url, json=payload)
        except Exception as e:
            print "ephemeral_message_request error "+str(e)

        # after sending a message to your currenet channel,
        #  then send another to the desired slack channel

        # creating json payload
        try:
            if sendto_slack_channel:
                payload = {
                    'text': sender_title +'_' + query + '_',
                    'as_user': False,
                    "channel": sendto_slack_channel,
                    "attachments": val,
                    'mrkdwn': 'true'
                }

                incoming_message_request = requests.post(sendto_webhook, json=payload)

                # if the slack message was not posted then send a message to sender
                if incoming_message_request.status_code != 200:
                    print (
                        'In send_to_slack ephemeral Slack returned status code %s, the response text is %s' % (
                            incoming_message_request.status_code, incoming_message_request.text)
                    )


                    send_message_to_slack('Unable to execute sendto command, retry with a valid user or channel')

        except Exception as e:
            print "sendto_message_request error "+str(e)







