import boto3
import json
import re
import math
import os.path
from datetime import *
#import common



def main(text):
	regionList = ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-2']
	region = regionList[0]
	cluster = ""
	ret = ""
	
	text.pop(0) # remove command name

	awsKeyId = None
	awsSecretKey = None
	awsSessionToken = None

	if os.path.isfile("./aws.config"):
	  with open("aws.config") as f:
	    accounts = json.load(f)
	    for account in accounts['Accounts']:
	    	if account['AccountName'] in text:
	    		text.remove(account['AccountName'])
	    		sts_client = boto3.client('sts')
	    		assumedRole = sts_client.assume_role(RoleArn=account['RoleArn'], RoleSessionName="AssumedRole")
	    		awsKeyId = assumedRole['Credentials']['AccessKeyId']
	    		awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
	    		awsSessionToken = assumedRole['Credentials']['SessionToken']


	session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey, aws_session_token=awsSessionToken)


	extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(text))
	if extractedRegion:
		region = extractedRegion.group()
		text.remove(region)

	eb = session.client("elasticbeanstalk", region_name=region)
	if 'list' in text:
		text.remove("list")
		ret = ""
		if 'applications' in text:
			try:
				applications = eb.describe_applications()['Applications']
			except Exception as e:
				print e
				return "Could not describe applications in " + region
			if len(applications) == 0:
				return "There are no beanstalk applications in this region: " + region

			for app in applications:
				ret = ret + app['ApplicationName'] + "\n"
				
			return ret
		elif 'environments' in text:
			text.remove("environments")
			application = None
			if len(text) > 0:
				application = " ".join(text)
			attachments = []
			environments = []
			try:
				if application == None:
					for env in eb.describe_environments()['Environments']:
						environments.append(env)
				else:
					for env in eb.describe_environments(ApplicationName=application)['Environments']:
						environments.append(env)

			except Exception as e:
				print e
				return "Application " + application + " was not found in region " + region

			if len(environments) == 0:
				return "There doesn't seem to be any environments in the application " + text[0]

			fields = []
			activeLoadBalancer = None
			if application != None and os.path.isfile("./aws.config"):
				with open("aws.config") as f:
					applications = json.load(f)
					for app in applications['Applications'][region]:
						if app['ApplicationName'] == application:
							r = session.client('route53', region_name=region)
							records = r.list_resource_record_sets(HostedZoneId=app['HostedZoneId'], StartRecordName=app['DNSRecord'], StartRecordType='A')
							
							activeLoadBalancer = records['ResourceRecordSets'][0]['AliasTarget']['DNSName']
			for env in environments:
				live = ""
				if activeLoadBalancer != None :
					if env['EndpointURL'].lower() in activeLoadBalancer.lower():
						live = ":white_check_mark:"
				status = ":healthy-environment:"
				health = env['Health']
				if health == 'Yellow':
					status = ":yellow_heart:"
				elif health == "Red":
					status = ":unhealthy-environment:"
				else:
					if env['Status'] == "Launching":
						status = ":rocket:"
					elif env['Status'] == "Updating":
						status = ":arrows_counterclockwise:"
					elif env['Status'] == "Terminating":
						status = ":warning:"
					elif env['Status'] == "Terminated":
						status = ":x:"
				fields.append({
						'title': env['EnvironmentName'] + " " + status + " " + live,
						'value': 'Version: ' + env['VersionLabel'],
						'short': True
					})

			attachments.append({
					'fallback': 'Environment List',
					'title': 'List of Environments',
					'fields': fields,
					'color': 'good'
				})
			return attachments

	elif 'describe' in text:
		text.remove('describe')
		attachments = []
		if 'application' in text:
			text.remove('application')
			environments = []
			try:
				environments = eb.describe_environments(ApplicationName=" ".join(text))['Environments']
			except Exception as e:
				print e
				return "Could not describe "+ " ".join(text) + " in " + region
			if len(environments) == 0:
				return "There are no beanstalk environments in this application: " + " ".join(text)

			fields = []
			for env in environments:
 			
				fields.append({
						'title': env['EnvironmentName'],
						'value': 'Version: ' + env['VersionLabel'],
						'short': True
					})

			attachments.append({
					'fallback': 'Environment List',
					'title': 'List of Environments',
					'fields': fields,
					'color': 'good'
				})
			return attachments

		elif 'environment' in text:
			text.remove("environment")
			environment = text.pop(0)

			attachments = []
			environments = []
			try:
				description = eb.describe_environments(EnvironmentNames=[environment])['Environments'][0]
			except Exception as e:
				print e
				return "Application " + application + " was not found in region " + region

			events = eb.describe_events(EnvironmentName=environment,
										MaxRecords=5, 
										Severity="WARN",
										StartTime=datetime.today() - timedelta(days=1))['Events']
			instances = eb.describe_environment_resources(EnvironmentName=environment)['EnvironmentResources']['Instances']
			fields = []
			
			version = description['VersionLabel']
			runningInstances = len(instances)
			fields.append({
					'title': 'Current Deployment',
					'value': 'Version: ' + version,
					'short': True
				})
			fields.append({
					'title': 'Running Instances',
					'value': str(runningInstances) + ' Instances',
					'short': True
				})
			fields.append({
					'title': 'Container Version',
					'value': description['SolutionStackName'],
					'short': True
				})
			fields.append({
					'title': 'Last Updated',
					'value': description['DateUpdated'].strftime("%d/%m at %H:%M"),
					'short': True
				})

			for event in events:
				fields.append({
						'title': event['Severity'] + " at " + event['EventDate'].strftime("%d/%m at %H:%M"),
						'value': event['Message'],
						'short': True
					})

			status = ":green_heart:"
			health = description['Health']
			if health == 'Yellow':
				status = ":yellow_heart:"
			elif health == "Red":
				status = ":heart:"
			else:
				if description['Status'] == "Launching":
					status = ":rocket:"
				elif description['Status'] == "Updating":
					status = ":arrows_counterclockwise:"
				elif description['Status'] == "Terminating":
					status = ":warning:"
				elif description['Status'] == "Terminated":
					status = ":x:"

			attachments.append({
					'fallback': 'Environment List',
					'title':  environment + " " + status,
					'fields': fields,
					'color': 'good'
				})
			return attachments 
	else:
		return "I did not understand the query. Please try again."

def about():
	return "This plugin returns requested information regarding AWS Elastic Beanstalk"

def information():
	return """This plugin returns various information about clusters and services hosted on ECS.
	The format of queries is as follows:
	jarvis eb list applications <region>
	jarvis eb list environments <application> <region>
	jarvis eb describe <application> <region>
	jarvis ecs describe <environment> <application> <region> """