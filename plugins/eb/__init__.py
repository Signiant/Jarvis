import boto3
import json
import re
import math
import os.path
from datetime import *
import common



def main(text):
	regionList = ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-2']
	region = regionList[0]
	
	text.pop(0) # remove command name
	if len(text) == 0:
		return "You did not supply a query to run"
	if text[0] == 'help':
		return information()

	awsKeyId = None
	awsSecretKey = None
	awsSessionToken = None
	loadedApplications = None
	tokens = []
	config = None
	if os.path.isfile("./aws.config"):
		with open("aws.config") as f:
			config = json.load(f)
		if config.get('Applications'):
			loadedApplications = config['Applications']

	if 'in' in text:
		while text[-1] != 'in':
			tokens.append(text.pop())
		extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(tokens))
		if extractedRegion:
			region = extractedRegion.group()
			tokens.remove(region)
		text.remove('in')

	if len(tokens) > 0 and config != None:
			for account in config['Accounts']:
				if account['AccountName'] in tokens:
					tokens.remove(account['AccountName'])
					sts_client = boto3.client('sts')
					assumedRole = sts_client.assume_role(RoleArn=account['RoleArn'], RoleSessionName="AssumedRole")
					awsKeyId = assumedRole['Credentials']['AccessKeyId']
					awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
					awsSessionToken = assumedRole['Credentials']['SessionToken']
					# Load application settings for this account
					if account.get('Applications'):
						loadedApplications = account['Applications']
			if len(tokens) > 0:
				return "Could not resolve " + " ".join(tokens)
	elif len(tokens) > 0:
		return "Could not locate aws.config file"

	session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey, aws_session_token=awsSessionToken)

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
				return "There doesn't seem to be any environments in the application " + application

			fields = []
			activeLoadBalancer = None

			if application != None and loadedApplications != None:
				for app in loadedApplications[region]:
					if app['ApplicationName'].lower() == application.lower():
						r = session.client('route53', region_name=region)
						records = r.list_resource_record_sets(HostedZoneId=app['HostedZoneId'], StartRecordName=app['DNSRecord'], StartRecordType='A')
							
						activeLoadBalancer = records['ResourceRecordSets'][0]['AliasTarget']['DNSName']

			for env in environments:
				live = ""
				if activeLoadBalancer != None :
					if env['EndpointURL'].lower() in activeLoadBalancer.lower():
						live = ":live-environment:"
				status = ":healthy-environment:"
				health = env['Health']
				if health == 'Yellow':
					status = ":unstable-environment:"
				elif health == "Red":
					status = ":failing-environment:"
				else:
					if env['Status'] == "Launching":
						status = ":rocket:"
					elif env['Status'] == "Updating":
						status = ":updating-environment:"
					elif env['Status'] == "Terminating":
						status = ":warning:"
					elif env['Status'] == "Terminated":
						status = ":x:"
				fields.append({
						'title': status + " " + env['EnvironmentName'] + " " + live,
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
			application = " ".join(text)
			environments = []
			try:
				environments = eb.describe_environments(ApplicationName=application)['Environments']
			except Exception as e:
				print e
				return "Could not describe "+ " ".join(text) + " in " + region
			if len(environments) == 0:
				return "There are no beanstalk environments in this application: " + " ".join(text)

			fields = []
			activeLoadBalancer = None
			if application != None and loadedApplications != None:
				for app in loadedApplications[region]:
					if app['ApplicationName'].lower() == application.lower():
						r = session.client('route53', region_name=region)
						records = r.list_resource_record_sets(HostedZoneId=app['HostedZoneId'], StartRecordName=app['DNSRecord'], StartRecordType='A')
							
						activeLoadBalancer = records['ResourceRecordSets'][0]['AliasTarget']['DNSName']

			for env in environments:
 				live = ""
				if activeLoadBalancer != None :
					if env['EndpointURL'].lower() in activeLoadBalancer.lower():
						live = ":live-environment:"
				status = ":healthy-environment:"
				health = env['Health']
				if health == 'Yellow':
					status = ":unstable-environment:"
				elif health == "Red":
					status = ":failing-environment:"
				else:
					if env['Status'] == "Launching":
						status = ":rocket:"
					elif env['Status'] == "Updating":
						status = ":updating-environment:"
					elif env['Status'] == "Terminating":
						status = ":warning:"
					elif env['Status'] == "Terminated":
						status = ":x:"
				fields.append({
						'title': status + " " + env['EnvironmentName'] + " "  + live,
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
			graph = False
			graphType = None
			if 'graph' in text:
				graph = True
				print len(text)
				print text.index('graph')
				if len(text) > text.index('graph') + 1:
					graphType = text[text.index('graph') + 1]

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
			resources = eb.describe_environment_resources(EnvironmentName=environment)['EnvironmentResources']
			instances = resources['Instances']
			loadBalancerName = None
			if len(resources['LoadBalancers']) > 0:
				loadBalancerName = resources['LoadBalancers'][0]['Name']
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

			status = ":healthy-environment:"
			health = description['Health']
			if health == 'Yellow':
				status = ":unstable-environment:"
			elif health == "Red":
				status = ":failing-environment:"
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
					'title':  status + " " + environment,
					'fields': fields,
					'color': 'good'
				})

			if graph != False and loadBalancerName != None:
				cw = session.client('cloudwatch', region_name=region)
				reqdata = []
				latdata = []
				timedata = None
				if graphType == None or graphType == 'requests':
					envrequests = cw.get_metric_statistics(	Namespace="AWS/ELB", 
															MetricName="RequestCount", 
															Dimensions=[{'Name': 'LoadBalancerName', 'Value': loadBalancerName}],
															StartTime=datetime.today() - timedelta(days=1),
															EndTime=datetime.today(),
															Period=1800,
															Statistics=['Sum'],
															Unit='Count')
					for datapoint in envrequests['Datapoints']:
						reqdata.append([datapoint['Timestamp'], datapoint['Sum']])
					reqdata = sorted(reqdata, key=lambda x: x[0])
					timedata = [i[0].strftime("%I%M") for i in reqdata]

				if graphType == None or graphType == 'latency':
					envlatency = cw.get_metric_statistics(	Namespace="AWS/ELB", 
															MetricName="Latency", 
															Dimensions=[{'Name': 'LoadBalancerName', 'Value': loadBalancerName}],
															StartTime=datetime.utcnow() - timedelta(days=1),
															EndTime=datetime.utcnow(),
															Period=1800,
															Statistics=['Average'],
															Unit='Seconds')
					for datapoint in envlatency['Datapoints']:
						latdata.append([datapoint['Timestamp'], datapoint['Average']])
					latdata = sorted(latdata, key=lambda x: x[0])
					if timedata == None:
						timedata = [i[0].strftime("%I%M") for i in latdata]

				attachments.append(common.create_graph('Graphing Environment Requests and Latency over 1 day', 
						'Requests (Count)', [i[1] for i in reqdata], 
						'Latency (Seconds)', [i[1] for i in latdata], 
						timedata))

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
	jarvis eb describe application <application> <region>
	jarvis eb describe environment <environment> <application> <region> [graph] [latency|requests] """
