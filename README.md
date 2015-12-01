# Jarvis
Jarvis is your personal AWS Slackbot. Currently, Jarvis can be used to find out information about ECS services running in AWS.

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

Under API Endpoints, choose to add an API endpoint from API Gateway. Fill in the form and select POST for the method.

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
