import imp
import os
from collections import defaultdict
from slacker import Slacker
import json

pluginFolder = "./plugins"
mainFile = "__init__"

with open(os.path.join(os.path.dirname(__file__), 'SLACK_BOT_API_TOKEN')) as f:
    bot_api_token = f.read().strip()
with open(os.path.join(os.path.dirname(__file__), 'SLACK_TEAM_TOKEN')) as f:
    incoming_token = f.read().strip()

slack = Slacker(bot_api_token)
slack_channel = '#general'
slack_bot_name="Jarvis"
as_user = True

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
    global slack_channel 
    slack_channel = '#{}'.format(param_map['channel_name'])
    retval = None

    if param_map['token'] != incoming_token:  # Check for a valid Slack token
        retval = 'invalid incoming Slack token'

    elif text[1] == 'help':
        if len(text) > 2:
            try:
                plugin = loadPlugin(text[2])
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
            plugin = loadPlugin(text[1])

            retval = plugin.main(text)
        except Exception as e:
            retval = "I'm afraid I did not understand that command. Use 'jarvis help' for available commands."
            print 'Error: ' + format(str(e))

    if isinstance(retval, basestring):
        post_slack_message(retval)
    else:
        post_slack_attachment(retval)

def post_slack_attachment(attachment):
    #print attachment
    slack.chat.post_message(slack_channel, "", username=slack_bot_name, attachments=json.dumps(attachment), as_user=as_user)


def post_slack_message(text):
    #print text
    slack.chat.post_message(slack_channel, text, username=slack_bot_name, as_user=as_user)
