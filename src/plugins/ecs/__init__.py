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
	cluster = ""
	ret = ""

	text.pop(0) # remove command name
	if len(text) == 0:
		return "You did not supply a query to run"
	if text[0] == 'help':
		return information()

	awsKeyId = None
	awsSecretKey = None
	awsSessionToken = None

	tokens = []
	if 'in' in text:
		while text[-1] != 'in':
			tokens.append(text.pop())
		extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(tokens))
		if extractedRegion:
			region = extractedRegion.group()
			tokens.remove(region)
		text.remove('in')

	if len(tokens) > 0 and os.path.isfile("./aws.config"):
		with open("aws.config") as f:
			config = json.load(f)
		for account in config['Accounts']:
			if account['AccountName'] in tokens:
				tokens.remove(account['AccountName'])
				sts_client = boto3.client('sts')
				assumedRole = sts_client.assume_role(RoleArn=account['RoleArn'], RoleSessionName="AssumedRole")
				awsKeyId = assumedRole['Credentials']['AccessKeyId']
				awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
				awsSessionToken = assumedRole['Credentials']['SessionToken']
		if len(tokens) > 0:
			return "Could not resolve " + " ".join(tokens)
	elif len(tokens) > 0:
		return "Could not locate aws.config file"

	session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey, aws_session_token=awsSessionToken)

	if 'regions' in text:
		if 'clusters' in text:
			for region in regionList[:]:
				ecs = session.client("ecs", region_name=region)
				ret = ecs.list_clusters()
				if len(ecs.list_clusters()['clusterArns']) == 0:
					regionList.remove(region)

		return " ".join(regionList)

	ecs = session.client("ecs", region_name=region)
	if 'list' in text:
		text.remove("list")
		ret = ""
		if 'clusters' in text:
			clusters = ecs.list_clusters()['clusterArns']
			if len(clusters) == 0:
				return "There are no clusters in this region: " + region
			for cluster in clusters:
				ret = ret + cluster.split('/')[-1] + '\n'

			return ret

		#see if tasks is in user command
		elif tasks_check_text(text):

			tasks_lookup_term = tasks_get_lookup_term(text)
			fields = []
			attachments = []

			if not text:
				return "I need a cluster name to complete the requested operation. To view the cluster names, use 'jarvis ecs list clusters <region>'"

			if 'running' in text:
				text.remove("running")

				try:
					resulting_array = get_task_list(cluster=text[0], ecs=ecs)
					query_result = ecs.describe_tasks(cluster=text[0], tasks=resulting_array)
					instance_task_families = parse_tasks(query_result['tasks'], tasks_lookup_term, ecs)

					if not instance_task_families:
						return "No tasks where found matching the lookup term for tasks. To look up a particular task, use 'jarvis ecs list tasks---<optional term> running <cluster> [in <region/account>]' "

					for tasks in instance_task_families:
						fields.append({
								'title': tasks,
								'value': 'Version: '+str(instance_task_families[tasks]['version'])+ '\nCount: '
										 + str(instance_task_families[tasks]['count']),
								'short': True
							})

					attachments.append({
						'fallback': 'List of Running Tasks',
						'title': 'List of Running Tasks',
						'fields': fields
					})	

					return attachments

				except Exception as e:
					print "exception in tasks option is "+str(e)
					return "Cluster " + text[0] + " was not found in region " + region

			else:
				return "No valid option for command jarvis ecs list tasks found. Please review /jarvis --help and try again."


		elif 'services' in text:
			text.remove("services")

			if len(text) == 0:
				return "I need a cluster name to complete the requested operation. To view the cluster names, use 'jarvis ecs list clusters <region>'"

			attachments = []
			fields = []

			try:
				sPaginator = ecs.get_paginator('list_services')
				sIterator = sPaginator.paginate(cluster=text[0])
				for cluster in sIterator:
					services = []
					for service in cluster['serviceArns']:
						services.append(service)

					if len(services) == 0:
						return "There doesn't seem to be any services in the cluster " + text[0]

					services_desc = ecs.describe_services(cluster=text[0], services=services)
					for service in services_desc['services']:
						image = ecs.describe_task_definition(taskDefinition=service['taskDefinition'])
						imagename = image['taskDefinition']['containerDefinitions'][0]['image'].split(':')[-1]
						servicename = service['serviceName'].split('/')[-1]
						ret = ret + servicename + "\t\t" + imagename + "\n"
						fields.append({
							'title': servicename,
							'value': 'Version: ' + imagename,
							'short': True
						})

				attachments.append({
					'fallback': 'Service List',
					'title': 'List of Services',
					'fields': fields
				})

				return attachments
			except Exception as e:
				print e
				return "Cluster " + text[0] + " was not found in region " + region


	elif 'describe' in text or 'desc' in text:
		cw = session.client('cloudwatch', region_name=region)
		text.pop(0)
		createGraph = False

		if "graph" in text:
			text.remove("graph")
			createGraph = True

		if len(text) == 1:
			clustername = text[0]

			clusters = ecs.describe_clusters(clusters=[clustername])

			if clusters['failures']:
				return "I could not find the cluster specified: " + clustername

			attachments = []

			clustercpu = cw.get_metric_statistics(	Namespace="AWS/ECS",
													MetricName="CPUUtilization",
													Dimensions=[{'Name': 'ClusterName', 'Value': clustername}],
													StartTime=datetime.today() - timedelta(days=1),
													EndTime=datetime.today(),
													Period=1800,
													Statistics=['Average'],
													Unit='Percent')

			clustermem = cw.get_metric_statistics(	Namespace="AWS/ECS",
													MetricName="MemoryUtilization",
													Dimensions=[{'Name': 'ClusterName', 'Value': clustername}],
													StartTime=datetime.utcnow() - timedelta(days=1),
													EndTime=datetime.utcnow(),
													Period=1800,
													Statistics=['Average'],
													Unit='Percent')

			cpudata = []
			memdata = []

			for datapoint in clustercpu['Datapoints']:
				cpudata.append([datapoint['Timestamp'], datapoint['Average']])

			for datapoint in clustermem['Datapoints']:
				memdata.append([datapoint['Timestamp'], datapoint['Average']])

			cpudata = sorted(cpudata, key=lambda x: x[0])
			memdata = sorted(memdata, key=lambda x: x[0])

			clustercpu = math.ceil(cpudata[0][1])
			clustercpu = int(clustercpu)
			clustermem = math.ceil(memdata[0][1])
			clustermem = int(clustermem)

			clusters = clusters['clusters'][0]

			fields = [{
						'title': 'Registered Instances',
						'value': clusters['registeredContainerInstancesCount'],
						'short': True
					}, {
						'title': 'Active Services',
						'value': clusters['activeServicesCount'],
						'short': True
					}, {
						'title': 'Running Tasks',
						'value': clusters['runningTasksCount'],
						'short': True
					}, {
						'title': 'Pending Tasks',
						'value': clusters['pendingTasksCount'],
						'short': True
					}]

			if not createGraph:
				fields.append({
						'title': 'Memory Usage',
						'value': str(clustermem) + "%",
						'short': True
					})
				fields.append({
						'title': 'CPU Usage',
						'value': str(clustercpu) + "%",
						'short': True
					})

			attachments.append({
					'fallback': 'Cluster: ' + clusters['clusterName'],
					'title': 'Cluster ' + clusters['clusterName'],
					'fields': fields,
					'color': 'good'
				})

			if createGraph:
				attachments.append(common.create_graph('Graphing Cluster CPU and Memory Usage over 1 day',
					'Cluster CPU', [i[1] for i in cpudata],
					'Cluster Memory', [i[1] for i in memdata],
					[i[0].strftime("%I%M") for i in cpudata]))

			return attachments
		elif len(text) == 2:
			attachments = []

			if len(text) < 2:
				return """I need a cluster name and a service name to complete the requested operation.
				To view the cluster names, use 'jarvis ecs list clusters <region>'
				To view the services, use 'jarvis ecs list services <cluster> <region>'"""

			matched = False
			matchedCount = 0
			servicename = text[0]
			clustername = text[1]
			try:
				services = ecs.list_services(cluster=text[1])['serviceArns']
			except Exception as e:
				print e
				return "Cluster " + text[1] + " was not found in region " + region

			for service in services:
				if text[0] in service and not matched:
					matched = True
					matchedCount+=1
					try:
						services_desc = ecs.describe_services(cluster=text[1],services=[service])
					except Exception as e:
						print e
						return "Cluster " + text[0] + " was not found in region " + region
					for service in services_desc['services']:
						image = ecs.describe_task_definition(taskDefinition=service['taskDefinition'])
						imagename = image['taskDefinition']['containerDefinitions'][0]['image'].split(':')[-1]
						servicename = service['serviceName'].split('/')[-1]
						attachments.append(
							{
								'fallback': 'Service ' + servicename,
								'title': servicename,
								'fields': [{
					    		    'title': 'Deployment',
					    		    'value': imagename,
					    		    'short': True
					   			}, {
					   				'title': 'Updated At',
					   				'value': service['deployments'][0]['updatedAt'].strftime("%Y-%m-%d %H:%M %z")
					   				,
					   				'short': True
					   			}, {
					   		 		'title': 'CPU Reservation',
					   		 		'value': str(image['taskDefinition']['containerDefinitions'][0]['cpu']) + " Units",
					   		 		'short': True
					    		}, {
					    			'title': 'Memory Reservation',
					    			'value': str(image['taskDefinition']['containerDefinitions'][0]['memory']) + " Megabytes",
					    			'short': True
					    		}, {
					    			'title': 'Running Tasks',
					    			'value': service['runningCount'],
					    			'short': True
					    		}],
								'color': 'good'
							}
						)
				elif text[0] in service and matched:
					matchedCount+=1
			if matchedCount > 1:
				attachments.append({
					'fallback': 'Service ' + servicename,
								'title': str(matchedCount) + ' Services Matched',
								'text': 'If this is not the service you asked for, you can list the services using jarvis ecs list services',
								'color': 'warning'
					})
			if matched:
				if createGraph:

					servicecpu = cw.get_metric_statistics(	Namespace="AWS/ECS",
												MetricName="CPUUtilization",
												Dimensions=[{'Name': 'ClusterName', 'Value': clustername}, {'Name': 'ServiceName', 'Value': servicename}],
												StartTime=datetime.today() - timedelta(days=1),
												EndTime=datetime.today(),
												Period=1800,
												Statistics=['Average'],
												Unit='Percent')

					cpudata = []

					for datapoint in servicecpu['Datapoints']:
						cpudata.append([datapoint['Timestamp'], datapoint['Average']])

					servicemem = cw.get_metric_statistics(	Namespace="AWS/ECS",
												MetricName="MemoryUtilization",
												Dimensions=[{'Name': 'ClusterName', 'Value': clustername}, {'Name': 'ServiceName', 'Value': servicename}],
												StartTime=datetime.today() - timedelta(days=1),
												EndTime=datetime.today(),
												Period=1800,
												Statistics=['Average'],
												Unit='Percent')

					memdata = []

					for datapoint in servicemem['Datapoints']:
						memdata.append([datapoint['Timestamp'], datapoint['Average']])


					memdata = sorted(memdata, key=lambda x: x[0])
					cpudata = sorted(cpudata, key=lambda x: x[0])

					attachments.append(common.create_graph("Graphing Service CPU and Memory Usage over 1 day",
						'Service CPU',
						[i[1] for i in cpudata],
						'Service Memory',
						[i[1] for i in memdata],
						[i[0].strftime("%I%M") for i in cpudata]))

				return attachments
			else:
				return "Could not find any services that include " + text[0]
	else:
		return "I did not understand the query. Please try again."

def about():
	return "This plugin returns requested information regarding AWS EC2 Container Service"

def information():
	return """This plugin returns various information about clusters and services hosted on ECS.
	The format of queries is as follows:
	jarvis ecs regions
	jarvis ecs list clusters [in <region/account>]
	jarvis ecs list services <cluster> [in <region/account>]
	jarvis ecs describe|desc <cluster> [in <region/account>]
	jarvis ecs describe|desc <service> <cluster> [in <region/account>]
	jarvis ecs list tasks[---<task_name_optional>] running <cluster> [in <region/account>]"""


# list the tasks in cluster
def get_task_list(next_token=None, cluster=None, ecs=None):
    ''' Get the running tasks '''
    running_tasks = []

    # Get tasks in this cluster
    query_result = ecs.list_tasks(cluster=cluster)

    if 'ResponseMetadata' in query_result:
        if 'HTTPStatusCode' in query_result['ResponseMetadata']:
            if query_result['ResponseMetadata']['HTTPStatusCode'] == 200:
                if 'nextToken' in query_result:
                    running_tasks.extend(get_task_list(next_token=query_result['nextToken']))
                else:
                    running_tasks.extend(query_result['taskArns'])
    return running_tasks


def parse_tasks(task_list, lookup_term, plugin):

    ''' Parse task_list and return a dict containing family:count'''
    task_families = {}
    for task in task_list:

        # Get the task type (service or family)
        type = task['group'].split(':')[0]
        # Get the task family for this task
        family = task['group'].split(':')[-1]

        image = plugin.describe_task_definition(taskDefinition=family)
        version_name = image['taskDefinition']['containerDefinitions'][0]['image'].split('/')[-1].split(':')[-1]

        if tasks_add_not_blank(family, lookup_term):
            if type == "family":
                if family not in task_families:
                    task_families[family] = {}
                    task_families[family]['count'] = 1
                    task_families[family]['version'] = version_name
                else:
                    task_families[family]['count'] = task_families[family]['count'] + 1

    return task_families


def tasks_add_not_blank(theword, lookup_word):

    if not lookup_word:
        return True
    else:
        if theword.lower().find(str(lookup_word.lower())) > -1:
            return True
        else:
            return False

# check to see if tasks word in arguments
def tasks_check_text(text):
    for data in text:
        if 'tasks' in data.lower().split('---'):
            return True


def tasks_get_lookup_term(text):
    for data in text:
        if 'tasks' in data.lower().split('---'):
            text.remove(data)
            if data.lower().split('---')[-1] == 'tasks':
                return None
            else:
                return data[(data.lower().find('---') + 3):]

