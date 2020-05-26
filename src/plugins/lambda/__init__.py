import boto3
import json
import re
import math
import os.path
from datetime import *
import common
import compare_output
from . import lambda_compares



def main(text):
    regionList = ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-2']
    region = regionList[0]
    cluster = ""
    ret = ""

    text.pop(0)  # remove command name
    if len(text) == 0:
        return "You did not supply a query to run"
    if text[0] == 'help':
        return information()

    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None
    the_account = None
    tokens = []
    if 'in' in text:
        while text[-1] != 'in':
            tokens.append(text.pop())
        extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(tokens))
        if extractedRegion:
            region = extractedRegion.group()
            tokens.remove(region)
        text.remove('in')

    # load default account from config
    config = None

    if os.path.isfile("./aws.config"):
        with open("aws.config") as f:
            config = json.load(f)
        if config.get('lambda'):
            for account in config['lambda']['Accounts']:
                if account["RoleArn"] == "" and account['AccountName'] == "":
                    loadedApplications = account['Clusters']

    if len(tokens) > 0 and config != None:
        for account in config['lambda']['Accounts']:
            if account['AccountName'] in tokens:
                the_account = account['AccountName']
                tokens.remove(account['AccountName'])
                if account['RoleArn']:
                    sts_client = boto3.client('sts')
                    assumedRole = sts_client.assume_role(RoleArn=account['RoleArn'], RoleSessionName="AssumedRole")
                    awsKeyId = assumedRole['Credentials']['AccessKeyId']
                    awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
                    awsSessionToken = assumedRole['Credentials']['SessionToken']
                    break
        if len(tokens) > 0:
            return "Could not resolve " + " ".join(tokens)
    elif len(tokens) > 0:
        return "Could not locate aws.config file"

    session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey,
                                    aws_session_token=awsSessionToken)
    if 'compare' in text:
        text.remove("compare")

        if "with" in text and len([_f for _f in text if _f]) > 6 and len([_f for _f in text if _f]) < 10:

            # extract arguments from text for master and team lambda data
            master_args = [_f for _f in text[:text.index("with")] if _f]
            team_args = [_f for _f in text[text.index("with") + 1:] if _f]

            master_args_eval = eval_args(master_args, regionList)
            team_args_eval = eval_args(team_args, regionList)

            if master_args_eval and team_args_eval:

                config = None
                # load config file
                if os.path.isfile("./aws.config"):
                    with open("aws.config") as f:
                        config = json.load(f)

                if config:
                    master_data = get_in_lambda_compare_data(config, master_args, master_args_eval)
                    team_data = get_in_lambda_compare_data(config, team_args, team_args_eval)
                else:
                    return "Config file was not loaded"

                if master_data and team_data:


                    compared_data = lambda_compares.main_lambda_check_versions(master_data,team_data)
                    print("still compare data")
                    print(team_data['team_name'],compared_data )
                    attachments = compare_output.slack_payload(compared_data, team_data['team_name'])
                    return attachments

                else:
                    return "Values were not retrieved"
            else:
                return "Invalid region or account information entered"
        else:
            return "Missing information to complete comparison"
    else:
        return "I did not understand the query. Please try again."


def about():
    return "This plugin returns requested information regarding AWS EC2 Container Service"


def information():
    return """This plugin returns various information about clusters and services hosted on ECS.
    The format of queries is as follows:
    jarvis lambda regions [sendto <user or channel>]
    jarvis lambda list services <cluster> [in <region/account>] [sendto <user or channel>]
    jarvis lambda compare [<cluster>] within <region> <account> with [<cluster>] within <region> <account> [sendto <user or channel>]"""


# list the tasks in cluster
def get_task_list(next_token=None, cluster=None, ecs=None):
    # Get the running tasks
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
    # Parse task_list and return a dict containing family:count
    task_families = {}
    for task in task_list:
        family = task['taskDefinitionArn'].split("/")[-1]
        try:
            image = plugin.describe_task_definition(taskDefinition=family)
        except Exception as e:
            print(("Error could not retrieve image " + str(e)))
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
def get_in_lambda_compare_data(config, args, args_eval):
    result = dict()

    # Depending on the arguments provided the values for cluster, region and account are determined as follows...

    # if the args_eval did not recieve a cluster from user than args_eval == 3
    # if the args_eval did recieve a cluster from user than args_eval == 4
    if args_eval == 3:
        result['cluster_name'] = None
        result['region_name'] = args[1]
        result['account'] = args[2]
    elif args_eval == 4:
        result['cluster_name'] = args[0]
        result['region_name'] = args[2]
        result['account'] = args[3]

    for account in config['lambda']['Accounts']:
        if account['AccountName'] == result['account']:
            result['RoleArn'] = account['RoleArn']
            for the_region in account['Clusters']:
                if the_region == result['region_name']:
                    if result['cluster_name'] == None:
                        result['cluster_name'] = account['Clusters'][the_region]['cluster_list']
                    result['task_definition_name'] = account['Clusters'][the_region]['task_only_service']
                    result['environment_code_name'] = account['Clusters'][the_region]['environment_code_name']
                    result['service_exclude_list'] = config['lambda']['service_exclude_list']
                    result['service_mapping_list'] = config['lambda']['service_mapping_list']
                    result['team_name'] = account['Clusters'][the_region]['team_name']
    if ('environment_code_name' in result) == False:
        for the_clusters in config['lambda']['Accounts']:
            for the_region in the_clusters['Clusters']:
                if the_region == result['region_name']:
                    if result['account'] == the_clusters['Clusters'][the_region]['team_name']:
                        if result['cluster_name'] == None:
                            result['cluster_name'] = the_clusters['Clusters'][the_region]['cluster_list']
                        result['task_definition_name'] = account['Clusters'][the_region]['task_only_service']
                        result['environment_code_name'] = the_clusters['Clusters'][the_region]['environment_code_name']
                        result['service_exclude_list'] = config['lambda']['service_exclude_list']
                        result['service_mapping_list'] = config['lambda']['service_mapping_list']
                        result['RoleArn'] = None
                        result['team_name'] = the_clusters['Clusters'][the_region]['team_name']

    # if no data was pulled from config file than return 0
    if len(result) <= 3:
        return 0

    return result


# inspect arguments entered by user
def eval_args(args, regionList):
    args = [_f for _f in args if _f]

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
