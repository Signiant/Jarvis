# Jarvis
Jarvis is your personal AWS Slackbot. Currently, Jarvis can be used to find out information about ECS services and Elastic Beanstalk environments running in AWS.

## Preparing
Clone the repository

``` git clone https://github.com/Signiant/Jarvis ```

CD into the Jarvis directory then install requirements in the current directory

``` pip install -r requirements.txt -t . ```

Create a file called SLACK_TEAM_TOKEN that contains your Slack team token

Optional: If you plan on using Jarvis on multiple aws accounts, include a file called aws.config
```json
{
    "Accounts": [
        {
            "AccountName": "KeyWord",
            "RoleArn": "arn:aws:iam::role/jarvis"
        }
    ]
}
```
Zip everything inside the Jarvis folder

``` zip -r lambda.zip * ```

## Deploying Jarvis to Lambda

Jarvis consists of a Lambda function in python which is installed behind API Gateway.  You'll need to configure API gateway to call the lambda function at a REST endpoint and upload to Lambda the zip that you created previously.

### IAM

Create an IAM Role that has a trusted relationship from AWS Lambda.

Create and attach a policy or more to the role that allows listing and describing from ECS and any other permissions that plugins need.

### Lambda
Create a new Lambda function and choose to upload a python zip, select the created zip and hit save.

Under API Endpoints, choose to add an API endpoint from API Gateway. Fill in the form, selecting POST for the method and Open for the security.

### API Gateway
Navigate to your created API Gateway entry for the Lambda function. Open the POST method then choose **Integration Request**

**This step turns the incoming request into a string within a json object that we can parse later on**

Under **Mapping Templates**, add a new entry that has *Content-Type* set to *application/x-www-form-urlencoded* then edit the mapping template to include:
``
{
    "formparams": $input.json("$")
}
``

**The following steps are done to stop slackbot from posting a 'null' message whenever a slash command is issued for this function**

Return to the POST method and select **Integration Response**

Use the arrow on the left to expand and reveal a section named **Mapping Templates**

Add an entry to *Content-Type* with a value of *application/json* and set the mapping template to:

``` #set($inputRoot = $input.path('$')) ```

Now, return to the POST method one more time and select **Method Response**

Use the arrow on the left to expand the 200 Response section and select *Add Response Model*

Set the *Content-Type* to *application/json* and the *Models* to *Empty*

Deploy your API when ready. Copy the URL shown to you. You will need that to set up your slash command in Slack.

### Slack

You will also need to configure your slash command on Slack to post the information to your API Gateway URL.

Go to *Configure Integrations* on your slack team then choose *Configured Integrations*

Find *Slash Commands* in the list presented to you, then choose *Add*

Set a command that you want to use to call Jarvis (ex. /jarvis) and set the URL to the previously copied URL from API Gateway

Set the *Method* to `POST` and finish by customizing the bot's name and icon.

Once that is done, issuing "/jarvis help" will display the available commands

## Creating plugins

To create a plugin, simply create a folder with the plugin name in the plugins folder. An example would be: `plugins/blame`

In the plugin folder, `blame` in this case, create a file named __init__.py.

This file is the entry point of your plugin. This python file MUST contain the following three functions:

`main(text)` The entry point to your plugin's main functionality. More on return values later.

`about()` This shows up when somebody asks Jarvis for help. Have it return a string that contains a brief description of what the plugin does.

`information()` This shows up when somebody asks for help on a specific plugin. This is where you return a string containing a more detailed explanation.

### main(text) return what?

There are two ways a plugin can return values to be posted into your slack.

The first method is just returning a string. This will just post said string on a slack channel.

The second method is by returning a Slack attachment object. The syntax is as follows:

```json
{
    "attachments": [
        {
            "fallback": "Required plain-text summary of the attachment.",

            "color": "#36a64f",

            "pretext": "Optional text that appears above the attachment block",

            "author_name": "Bobby Tables",
            "author_link": "http://flickr.com/bobby/",
            "author_icon": "http://flickr.com/icons/bobby.jpg",

            "title": "Slack API Documentation",
            "title_link": "https://api.slack.com/",

            "text": "Optional text that appears within the attachment",

            "fields": [
                {
                    "title": "Priority",
                    "value": "High",
                    "short": false
                }
            ],

            "image_url": "http://my-website.com/path/to/image.jpg",
            "thumb_url": "http://example.com/path/to/thumb.png"
        }
    ]
}
```

More information on the syntax of attachments can be found at: https://api.slack.com/docs/attachments

## Configuring aws.config for the EB, ECS and s3 plugins

The EB, ECS and s3 plugins make use of an aws.config file to assume roles in different accounts. The syntax of the config file is as follows:

Note: We use a BlueGreen Deployment release technique on Elastic Beanstalk. In order to find out which is the `live` environment, the config file contains an `Applications` section that contains the Application Name, Hosted Zone ID, and DNS Record to figure out which environment is the `live` environment by looking at which load balancer the Route53 record set is pointing to.

The `Applications` key at the same level as the `Accounts` key is the `default account`. i.e. the same account where Jarvis is running.

```json
{
	"Accounts": [{
		"AccountName": "KeyWord",
		"RoleArn": "arn:aws:iam::role/jarvis”,
		"Applications": {
			"us-east-1": [{
				"ApplicationName": “ApplicationName”,
				"HostedZoneId": “ZXXXXXXXXXX”,
				"DNSRecord": “something.somewhere.com”
			}],
			"us-west-1": [{
				"ApplicationName": “ApplicationName”,
				"HostedZoneId": “ZXXXXXXXXXX”,
				"DNSRecord": “something.somewhere.com”
			}]
		}
	}],
	"Applications": {
		"eu-west-1": [{
			"ApplicationName": “ApplicationName”,
				"HostedZoneId": “ZXXXXXXXXXX”,
				"DNSRecord": “something.somewhere.com”
		}]
	}
}
```
