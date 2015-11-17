import boto3
import json
import re
import math
from datetime import *

session = boto3.session.Session()

def main(text):
	regionList = ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-2']
	region = regionList[0]
	cluster = ""
	ret = ""
	text.pop(0) # remove bot name
	text.pop(0) # remove command name
	extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(text))
	if extractedRegion:
		region = extractedRegion.group()
		text.remove(region)

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
		elif 'services' in text:
			text.remove("services")

			if len(text) == 0:
				return "I need a cluster name to complete the requested operation. To view the cluster names, use 'jarvis ecs list clusters <region>'"
			attachments = []
			services = []
			try:

				for service in ecs.list_services(cluster=text[0])['serviceArns']:
					services.append(service)

			except Exception as e:
				print e
				return "Cluster " + text[0] + " was not found in region " + region
			if len(services) == 0:
				return "There doesn't seem to be any services in the cluster " + text[0]


			services_desc = ecs.describe_services(cluster=text[0],services=services)
			fields = []
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
					'fields': fields,
					'color': 'good'
				})
			return attachments

	elif 'describe' in text:
		cw = session.client('cloudwatch')
		text.remove("describe")
		ret = ""
		if len(text) == 1:
			clustername = text[0]

			clusters = ecs.describe_clusters(clusters=[clustername])

			if clusters['failures']:
				return "I could not find the cluster specified: " + clustername

			attachments = []

			year = datetime.today().year
			month = datetime.today().month
			day = datetime.today().day
			hour = datetime.today().hour
			minute = datetime.today().minute

			clustercpu = cw.get_metric_statistics(	Namespace="AWS/ECS", 
													MetricName="CPUUtilization", 
													Dimensions=[{'Name': 'ClusterName', 'Value': clustername}],
													StartTime=datetime(year, month, day, hour, minute-5),
													EndTime=datetime(year, month, day, hour, minute),
													Period=300,
													Statistics=['Average'],
													Unit='Percent')

			clustermem = cw.get_metric_statistics(	Namespace="AWS/ECS", 
													MetricName="MemoryUtilization", 
													Dimensions=[{'Name': 'ClusterName', 'Value': clustername}],
													StartTime=datetime(year, month, day, hour, minute-5),
													EndTime=datetime(year, month, day, hour, minute),
													Period=300,
													Statistics=['Average'],
													Unit='Percent')

			clustercpu = math.ceil(clustercpu['Datapoints'][0]['Average'])
			clustercpu = int(clustercpu)
			clustermem = math.ceil(clustermem['Datapoints'][0]['Average'])
			clustermem = int(clustermem)

			clusters = clusters['clusters'][0]

			attachments.append({
					'fallback': 'Cluster: ' + clusters['clusterName'],
					'title': 'Cluster ' + clusters['clusterName'],
					'fields': [{
						'title': 'Registered Instances',
						'value': clusters['registeredContainerInstancesCount'],
						'short': True
					}, {
						'title': 'CPU Usage',
						'value': str(clustercpu) + "%",
						'short': True
					}, {
						'title': 'Memory Usage',
						'value': str(clustermem) + "%",
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
					}],
					'color': 'good'
				})
			return attachments
		elif len(text) == 2:
			attachments = []
			if len(text) < 2:
				return """I need a cluster name and a service name to complete the requested operation. 
				To view the cluster names, use 'jarvis ecs list clusters <region>'
				To view the services, use 'jarvis ecs list services <cluster> <region>'"""

			matched = False
			matchedCount = 0
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
	jarvis ecs list clusters <region>
	jarvis ecs list services <cluster> <region>
	jarvis ecs describe <cluster> <region>
	jarvis ecs describe <service> <cluster> <region> """
