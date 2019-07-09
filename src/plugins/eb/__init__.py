import boto3
import json
import re
import os.path
from datetime import *
import compare_output
import common
from . import eb_compares


def main(text):
    regionList = ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-2']
    region = regionList[0]

    text.pop(0)  # remove command name
    if len(text) == 0:
        return "You did not supply a query to run"
    if text[0] == 'help':
        return information()

    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None
    loadedApplications = None
    tokens = []

    if 'in' in text:
        while text[-1] != 'in':
            tokens.append(text.pop())
        extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(tokens))
        if extractedRegion:
            region = extractedRegion.group()
            tokens.remove(region)
        text.remove('in')

    config = None
    if os.path.isfile("./aws.config"):
        with open("aws.config") as f:
            config = json.load(f)
        if config.get('eb'):
            for account in config['eb']['Accounts']:
                if account["RoleArn"] == "":
                    if account['AccountName'] in tokens:
                        tokens.remove(account['AccountName'])
                        loadedApplications = account['Applications']
                        break
                    elif len(tokens) == 0:
                        loadedApplications = account['Applications']
                        break

    if len(tokens) > 0 and config != None:
        for account in config['eb']['Accounts']:
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

    session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey,
                                    aws_session_token=awsSessionToken)

    eb = session.client("elasticbeanstalk", region_name=region)

    if 'list' in text:
        text.remove("list")
        ret = ""
        if 'applications' in text or 'apps' in text:
            try:
                applications = eb.describe_applications()['Applications']
            except Exception as e:
                print(e)
                return "Could not describe applications in " + region
            if len(applications) == 0:
                return "There are no beanstalk applications in this region: " + region
            for app in applications:
                ret = ret + app['ApplicationName'] + "\n"
            return ret
        elif 'environments' in text or 'envs' in text:
            text.pop(0)
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
                print(e)
                return "Application " + application + " was not found in region " + region

            if len(environments) == 0:
                return "There doesn't seem to be any environments in the application " + application

            fields = []
            activeLoadBalancer = None

            if application != None and loadedApplications != None:
                for app in loadedApplications[region]:
                    if app['ApplicationName'].lower() == application.lower():
                        try:
                            if app.get('Account'):
                                for account in config['Accounts']:
                                    print("Looping")
                                    if account['AccountName'] == app['Account']:
                                        sts_client = boto3.client('sts')
                                        assumedRole = sts_client.assume_role(RoleArn=account['RoleArn'],
                                                                             RoleSessionName="AssumedRole")
                                        awsKeyId = assumedRole['Credentials']['AccessKeyId']
                                        awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
                                        awsSessionToken = assumedRole['Credentials']['SessionToken']

                                        session_temp = boto3.session.Session(aws_access_key_id=awsKeyId,
                                                                             aws_secret_access_key=awsSecretKey,
                                                                             aws_session_token=awsSessionToken)

                                        r = session_temp.client('route53', region_name=region)
                            else:
                                r = session.client('route53', region_name=region)

                            records = r.list_resource_record_sets(HostedZoneId=app['HostedZoneId'],
                                                                  StartRecordName=app['DNSRecord'], StartRecordType='A')

                            activeLoadBalancer = records['ResourceRecordSets'][0]['AliasTarget']['DNSName']
                        except:
                            pass
            for env in environments:
                live = ""
                if activeLoadBalancer != None:
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

    elif 'compare' in text:
        text.remove("compare")

        if "with" in text and len([_f for _f in text if _f]) == 7:
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
                    master_data = get_in_eb_compare_data(config, master_args, master_args_eval)
                    # print(master_data)
                    team_data = get_in_eb_compare_data(config, team_args, team_args_eval)
                    # print(team_data)
                else:
                    return "Config file was not loaded"

                if master_data and team_data:

                    superjenkins_data = common.get_superjenkins_data(config["General"]["script_tags"]["beginning_tag"],
                                                                     config["General"]["script_tags"]["ending_tag"],
                                                                     config["General"]["build_link"],
                                                                     config["General"]["my_build_key"])

                    if superjenkins_data:
                        compared_data = eb_compares.main_eb_check_versions(master_data,
                                                                           team_data,
                                                                           superjenkins_data,
                                                                           config["General"]["jenkins"][
                                                                               "branch_equivalent_tags"])
                        print(compared_data)
                        # this uses compare_output
                        attachments = compare_output.slack_payload(compared_data, team_data['team_name'])

                        return attachments

                else:
                    return "Values could not be retrieved from operation, 'Jarvis eb help'"
            else:
                return "Invalid region or account information entered"
        else:
            return "Invalid arguments entered to complete comparison"

    elif 'describe' in text or 'desc' in text:
        text.pop(0)
        attachments = []
        if 'application' in text or 'app' in text:
            text.pop(0)
            application = " ".join(text)
            environments = []
            try:
                environments = eb.describe_environments(ApplicationName=application)['Environments']
            except Exception as e:
                print(e)
                return "Could not describe " + " ".join(text) + " in " + region
            if len(environments) == 0:
                return "There are no beanstalk environments in this application: " + " ".join(text)

            fields = []
            activeLoadBalancer = None
            if application != None and loadedApplications != None:
                for app in loadedApplications[region]:
                    if app['ApplicationName'].lower() == application.lower():
                        try:
                            if app.get('Account'):
                                for account in config['Accounts']:
                                    print("Looping")
                                    if account['AccountName'] == app['Account']:
                                        sts_client = boto3.client('sts')
                                        assumedRole = sts_client.assume_role(RoleArn=account['RoleArn'],
                                                                             RoleSessionName="AssumedRole")
                                        awsKeyId = assumedRole['Credentials']['AccessKeyId']
                                        awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
                                        awsSessionToken = assumedRole['Credentials']['SessionToken']

                                        session_temp = boto3.session.Session(aws_access_key_id=awsKeyId,
                                                                             aws_secret_access_key=awsSecretKey,
                                                                             aws_session_token=awsSessionToken)

                                        r = session_temp.client('route53', region_name=region)
                            else:
                                r = session.client('route53', region_name=region)

                            records = r.list_resource_record_sets(HostedZoneId=app['HostedZoneId'],
                                                                  StartRecordName=app['DNSRecord'], StartRecordType='A')

                            activeLoadBalancer = records['ResourceRecordSets'][0]['AliasTarget']['DNSName']
                        except:
                            pass
            for env in environments:
                live = ""
                if activeLoadBalancer != None:
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

        elif 'environment' in text or 'env' in text:
            text.pop(0)
            environment = text.pop(0)
            graph = False
            graphType = None
            if 'graph' in text:
                graph = True
                print((len(text)))
                print((text.index('graph')))
                if len(text) > text.index('graph') + 1:
                    graphType = text[text.index('graph') + 1]

            attachments = []
            environments = []
            try:
                description = eb.describe_environments(EnvironmentNames=[environment])['Environments'][0]
            except Exception as e:
                print(e)
                return "Environment " + environment + " was not found in region " + region

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
                'title': status + " " + environment,
                'fields': fields,
                'color': 'good'
            })

            if graph != False and loadBalancerName != None:
                cw = session.client('cloudwatch', region_name=region)
                reqdata = []
                latdata = []
                timedata = None
                if graphType == None or graphType == 'requests':
                    envrequests = cw.get_metric_statistics(Namespace="AWS/ELB",
                                                           MetricName="RequestCount",
                                                           Dimensions=[
                                                               {'Name': 'LoadBalancerName', 'Value': loadBalancerName}],
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
                    envlatency = cw.get_metric_statistics(Namespace="AWS/ELB",
                                                          MetricName="Latency",
                                                          Dimensions=[
                                                              {'Name': 'LoadBalancerName', 'Value': loadBalancerName}],
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

    elif 'unpause' in text or 'unp' in text:
        text.pop(0)
        environment = " ".join(text)
        message = "Environment " + environment + " has been unpaused"

        try:
            resources = eb.describe_environment_resources(EnvironmentName=environment)['EnvironmentResources']
        except Exception as e:
            print(e)
            return "Environment " + environment + " was not found in region " + region

        autoscalerName = resources['AutoScalingGroups'][0]['Name']
        asClient = session.client('autoscaling', region_name=region)
        autoscaler = asClient.describe_auto_scaling_groups(AutoScalingGroupNames=[autoscalerName])['AutoScalingGroups'][
            0]

        if autoscaler['MaxSize'] != 0 or autoscaler['MinSize'] != 0:
            return "Environment " + environment + " is not currently paused"

        autoscalerTags = autoscaler['Tags']

        try:
            minInstances = int(next((tag['Value'] for tag in autoscalerTags if tag['Key'] == 'pause:max-instances')))
            maxInstances = int(next((tag['Value'] for tag in autoscalerTags if tag['Key'] == 'pause:min-instances')))
        except Exception as e:
            minInstances = 1
            maxInstances = 1
            message += "\nTags were missing for instance size on the autoscaling group, max and min instances set to a default of 1"

        try:
            asClient.update_auto_scaling_group(
                AutoScalingGroupName=autoscalerName,
                MinSize=minInstances,
                MaxSize=maxInstances
            )
        except Exception as e:
            print(e)
            return "Unable to unpause environment " + environment

        return message

    else:
        return "I did not understand the query. Please try again."


def about():
    return "This plugin returns requested information regarding AWS Elastic Beanstalk"


def information():
    return """This plugin returns various information about clusters and services hosted on ECS.
    The format of queries is as follows:
    jarvis eb list applications|apps <in region/account> [sendto <user or channel>]
    jarvis eb list environments|envs <application> <in region/account> [sendto <user or channel>]
    jarvis eb describe|desc application|app <application> <in region/account> [sendto <user or channel>]
    jarvis eb describe|desc environment|env <environment> <graph> <latency|requests> <in region/account> [sendto <user or channel>]
    jarvis eb unpause|unp <environment> <in region/account> [sendto <user or channel>]
    jarvis eb compare within <region> <account> with within <region> <account> [sendto <user or channel>]"""


def eval_args(args,regionList):

    args = [_f for _f in args if _f]

    if args.index("within") == 0:
        if args[1] in regionList and len(args) == 3:
            return 1
        else:
            return 0
    else:
        return 0


# get the dev account role for specified account_name
def config_get_account_rolearn(account_name, config):
    role_arn = None
    for account in config['eb']['Accounts']:
        if account['AccountName'] == account_name:
            role_arn = account['RoleArn']
            return role_arn
    return role_arn


def get_in_eb_compare_data(config, args, args_eval):
    result = dict()
    original_config = config
    if config.get('eb'):
        config = config['eb']['Accounts']

        # both region and account found
        if args_eval == 1:
            result['account'] = args[2]
            result['region_name'] = args[1]
            for account in config:

                if account['AccountName'] == result['account']:
                    result['RoleArn'] = account['RoleArn']
                    temp_holder = dict()
                    for the_region in account['Applications']:
                        if the_region == result['region_name']:
                            result['environments'] = account['Applications'][the_region]
                            for envs in account['Applications'][the_region]:
                                if "Account" in envs:
                                    # if an alternate account is specifed for the environment than put the
                                    # appropriate role_arn data for that environment
                                    temp_holder[envs['ApplicationName']] = {'dns_name': envs['DNSRecord'],
                                                                            'zone_id': envs['HostedZoneId'],
                                                                            'build_master_tag': envs['build_master_tag'],
                                                                            'alternate_role_arn': config_get_account_rolearn(
                                                                                envs['Account'], original_config)}
                                else:
                                    temp_holder[envs['ApplicationName']] = {'dns_name': envs['DNSRecord'],
                                                                            'zone_id': envs['HostedZoneId'],
                                                                            'build_master_tag': envs['build_master_tag']}
                                if 'team_name' in envs:
                                    result['team_name'] = envs["team_name"]
                                result['environments'] = temp_holder
            if ('team_name' in result) == False:
                temp_holder = dict()
                for account in config:
                    if account['RoleArn'] == "" and account['AccountName'] == "":
                        for the_region in account['Applications']:
                            if the_region == result['region_name']:
                                for envs in account['Applications'][the_region]:
                                    temp_holder[envs['ApplicationName']] = {'dns_name': envs['DNSRecord'],
                                                                                'zone_id': envs['HostedZoneId'],
                                                                                'build_master_tag': envs['build_master_tag']}
                                    if 'team_name' in envs:
                                        if envs['team_name'] == result['account']:
                                            result['RoleArn'] = None
                                            result['team_name'] = envs['team_name']
                                result['environments'] = temp_holder

        # if config data was not extracted then return zero
        if len(result) <= 2:
            return 0

        return result
