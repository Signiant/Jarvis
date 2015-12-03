import imp
import os
from collections import defaultdict
import requests
import urllib

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
    # Lambda entry point
    param_map = _formparams_to_dict(event['formparams'])
    text = param_map['text'].split('+')
    global query
    query = " ".join(text)
    global slack_channel 
    slack_channel = param_map['channel_id']
    retval = None

    global slack_response_url
    slack_response_url = param_map['response_url']
    slack_response_url = urllib.unquote(slack_response_url)

    print "LOG: The request came from: " + slack_channel
    print "LOG: The request is: " + str(text)
    print "LOG: The requesting user is: " + param_map['user_name']

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
            plugin = loadPlugin(text[0])
            retval = plugin.main(text)
        except Exception as e:
            retval = "I'm afraid I did not understand that command. Use 'jarvis help' for available commands."
            print 'Error: ' + format(str(e))

    post_to_slack(retval)
    
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