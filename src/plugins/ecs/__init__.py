import boto3
import json
import re
import math
import os.path
import requests
import logging
import pprint
import sys
from datetime import *
import common
import compare_output

#append path of ecs_compares module to sys.path
dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path)
import ecs_compares


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

	#load default account from config
	config = None

	if os.path.isfile("./aws.config"):
		with open("aws.config") as f:
			config = json.load(f)
		if config.get('ecs'):
			for account in config['ecs']['Accounts']:
				if "AccountName" not in account and "RoleArn" not in account:
					loadedApplications = account

	if len(tokens) > 0 and config != None:
		for account in config['ecs']['Accounts']:
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

	elif 'compare' in text:
		text.remove("compare")
		
		if "with" in text and len(filter(None, text)) > 6 and len(filter(None, text)) < 10:

			#extract arguments from text for master and team ecs data
			master_args = filter(None, text[:text.index("with")])
			team_args = filter(None, text[text.index("with") + 1:])

			master_args_eval = eval_args(master_args, regionList)
			team_args_eval = eval_args(team_args, regionList)

			if master_args_eval and team_args_eval:

				config = None
				#load config file
				if os.path.isfile("./aws.config"):
					with open("aws.config") as f:
						config = json.load(f)

				if config:
					master_data = get_in_ecs_compare_data(config, master_args, master_args_eval)
					team_data = get_in_ecs_compare_data(config, team_args, team_args_eval)
				else:
					return "Config file was not loaded"

				if master_data and team_data:

					# retrieves the json from superjenkins with all build link data
					superjenkins_data = common.get_superjenkins_data(config["General"]["script_tags"]["beginning_tag"],
															  config["General"]["script_tags"]["ending_tag"],
															  config["General"]["build_link"],
															  config["General"]["my_build_key"])

					compared_data = ecs_compares.main_ecs_check_versions(master_data,
															team_data,
															config["General"]["jenkins"]["branch_equivalent_tags"],
															superjenkins_data,
															team_data['service_exclude_list'])

					attachments = compare_output.slack_payload(compared_data, team_data['team_name'])
					return attachments

				else:
					return "Values were not retrieved"
			else:
				return "Invalid region or account information entered"
		else:
			return "Missing information to complete comparison"

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
	jarvis ecs regions [sendto <user or channel>]
	jarvis ecs list clusters [in <region/account>] [sendto <user or channel>]
	jarvis ecs list services <cluster> [in <region/account>] [sendto <user or channel>]
	jarvis ecs describe|desc <cluster> [in <region/account>] [sendto <user or channel>]
	jarvis ecs describe|desc <service> <cluster> [in <region/account>] [sendto <user or channel>]
	jarvis ecs list tasks[---<task_name_optional>] running <cluster> [in <region/account>] [sendto <user or channel>]
	jarvis ecs compare [<cluster>] within <region> <account> with [<cluster>] within <region> <account> [sendto <user or channel>]"""



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
		family = task['taskDefinitionArn'].split("/")[-1]
		try:
			image = plugin.describe_task_definition(taskDefinition=family)
		except Exception as e:
			print "Error could not retrieve image "+str(e)
			image = []
		if image:
			version_name = image['taskDefinition']['containerDefinitions'][0]['image'].split('/')[-1].split(':')[-1]
			if tasks_add_not_blank(family, lookup_term):
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



# retrieve data from config files for compare
def get_in_ecs_compare_data(config, args, args_eval):
	result = dict()

	# Depending on the arguments provided the values for cluster, region and account are determined as follows...

	#	if the args_eval did not recieve a cluster from user than args_eval == 3
	#	if the args_eval did recieve a cluster from user than args_eval == 4
	if args_eval == 3:
		result['cluster_name'] = None
		result['region_name'] = args[1]
		result['account'] = args[2]
	elif args_eval == 4:
		result['cluster_name'] = args[0]
		result['region_name'] = args[2]
		result['account'] = args[3]

	for account in config['ecs']['Accounts']:
		if account['AccountName'] == result['account']:
			result['RoleArn'] = account['RoleArn']
			for the_region in account['Clusters']:
				if the_region == result['region_name']:
					if result['cluster_name'] == None:
						result['cluster_name'] = account['Clusters'][the_region]['cluster_list']
					result['environment_code_name'] = account['Clusters'][the_region]['environment_code_name']
					result['service_exclude_list'] = config['ecs']['service_exclude_list']
					result['team_name'] = account['Clusters'][the_region]['team_name']
	if result.has_key('environment_code_name') == False:
		for the_clusters in config['ecs']['Accounts']:
			for the_region in the_clusters['Clusters']:
				if the_region == result['region_name']:
					if result['account'] == the_clusters['Clusters'][the_region]['team_name']:
						if result['cluster_name'] == None:
							result['cluster_name'] = the_clusters['Clusters'][the_region]['cluster_list']
						result['environment_code_name'] = the_clusters['Clusters'][the_region]['environment_code_name']
						result['service_exclude_list'] = config['ecs']['service_exclude_list']
						result['RoleArn'] = None
						result['team_name'] = the_clusters['Clusters'][the_region]['team_name']

	# if no data was pulled from config file than return 0
	if len(result) <= 3:
		return 0

	return result


#inspect arguments entered by user
def eval_args(args,regionList):
	args = filter(None, args)

	if args.index("within") == 1:
		if args[2] in regionList:
			if len(args) == 4:
				return len(args)
	elif args.index("within") == 0:
		if args[1] in regionList:
			if len(args) == 3:
				return len(args)
	else:
		return 0
