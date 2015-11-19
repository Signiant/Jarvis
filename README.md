# Jarvis
Jarvis is your personal AWS Slackbot. Currently, Jarvis can be used to find out information about ECS services running in AWS.

## Installing Jarvis

Jarvis consists of a Lambda function in python which is installed behind API Gateway.  You'll need to configure API gateway
 to call the lambda function at a REST endpoint and upload to Lambda the zip of what is here PLUS 2 files:
 
- SLACK_TEAM_TOKEN: Must contain the token for an INCOMING webhook allowing posting to slack
- SLACK_BOT_API_TOKEN: Must contain the unique token for your slackbot

Once installed, issuing "jarvis help" will display the available commands

Better documentation is coming soon :)
