import boto3
import logging
import re
import time
import requests


# get ecs data from boto call
def lambda_check_versions(region_name,role_arn,env_name,exclude_list,mapping_list):

    service_versions_dict = {}
    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None

    sts_client = boto3.client('sts')
    if role_arn:
        assumedRole = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="AssumedRole")
        awsKeyId = assumedRole['Credentials']['AccessKeyId']
        awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
        awsSessionToken = assumedRole['Credentials']['SessionToken']
    session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey,
                                    aws_session_token=awsSessionToken)


    try:
        client = session.client("lambda", region_name=region_name)
        if client:
            lambda_function_paginator = client.get_paginator('list_functions')
            lambda_iterator = lambda_function_paginator.paginate()
    except Exception as e:
        print(("Error obtaining list of lambda services for " + region_name + " (" + str(e) + ")"))
    except KeyError as e:
        print(("Key " + e + "not found"))

    for lambda_funcs in lambda_iterator:
        print(lambda_funcs)
        for lambda_func in lambda_funcs['Functions']:
            # print(lambda_func)
            lambda_data = extract_tag_env_var(client, lambda_func,region_name,exclude_list,mapping_list)
            if lambda_data:
                # print(env_name, lambda_data['environment_code_name'])
                if lambda_data['environment_code_name'] == env_name:
                    service_versions_dict[lambda_data['servicename']]=lambda_data

    print("service {0} {1}".format(len(service_versions_dict), service_versions_dict))
    return service_versions_dict


def extract_tag_env_var(lambda_client,lambda_function, region,exclude_list,mapping_list):
    """
    At moment we only want lambda that have the following tags:
    signiant-environment
    signiant-product
    signiant-owner
    signiant-service
    (signiant-build-tag)
    :param lambda_client:
    :param storage_dict:
    :param function_list:
    :return:
    """
    tag_list = lambda_client.list_tags(Resource=lambda_function['FunctionArn'])
    lambda_data={}
    required_tags = ('signiant-environment','signiant-product', 'signiant-owner', 'signiant-service','signiant-build-tag')
    if all(k in tag_list['Tags'] for k in required_tags):
        # print(tag_list['Tags']['signiant-build-tag'])
        print(lambda_function['FunctionName'])
        print(tag_list['Tags'])
        if not any(x in lambda_function['FunctionName'] for x in exclude_list):

            if tag_list['Tags']['signiant-service'] in mapping_list:
                #speical case mapping where the service name not match repo name in bitbucket. check aws.config map list
                lambda_data['servicename'] = mapping_list[tag_list['Tags']['signiant-service']]
            else:
                lambda_data['servicename']= tag_list['Tags']['signiant-service']

            lambda_data['regionname'] = region
            lambda_data['environment_code_name']=tag_list['Tags']['signiant-environment']
            lambda_data['lambda_name']=lambda_function['FunctionName']

            if tag_list['Tags']['signiant-build-tag'] != "no-build-tag":
                build_tag_list=tag_list['Tags']['signiant-build-tag'].split()
                if len(build_tag_list)==2:
                    bb_pipe_num = build_tag_list[1]
                    lambda_data['pipeline_num'] = bb_pipe_num
                    lambda_data['bb_hash'] = get_bb_hash(tag_list['Tags']['signiant-service'], bb_pipe_num)
                elif len(build_tag_list)==1 and build_tag_list[0].isdigit():
                    # special case where branch name does not exist in tag.
                    bb_pipe_num = build_tag_list[0]
                    lambda_data['pipeline_num'] = bb_pipe_num
                    lambda_data['bb_hash'] = get_bb_hash(tag_list['Tags']['signiant-service'], bb_pipe_num)
                    print("unique number tag")
                else:
                    # no proper signiant-build-tag under tag
                    lambda_data['pipeline_num'] = "no-proper-tag-num"
                    lambda_data['bb_hash'] = "no-proper-tag-hash"
                    print("still no proper tag")

            else:
                lambda_data['pipeline_num'] = "no-build-tag-num"
                lambda_data['bb_hash'] = "no-build-tag-hash"

            return lambda_data
    else:
        # not a prod lambda
        return False


def get_bb_hash(repo, pipe_num):
    """
    given repo and pipeline number find the commit hash number for a build
    :param repo:
    :param pipe_num:
    :return:
    """
    api_token = get_bb_credential()
    bb_api_url="https://api.bitbucket.org/2.0/repositories/signiant/{0}/pipelines/{1}".format(repo, pipe_num)
    headers = dict()
    headers['Authorization'] = "Bearer {0}".format(api_token)
    headers['Content-Type'] = 'application/json'
    api_response = requests.get(bb_api_url, headers=headers)

    if api_response.status_code == 200:
        api_response = api_response.json()
        return(api_response['target']['commit']['hash'][0:7])
    else:
        # if api to specific repo cannot be verified set it to false at moment
        print("bitbucket api 404 response {0} {1}".format(repo, pipe_num))
        print(api_response.json())
        return "Not_Found"


def get_versions_from_image(session,region_name,image, slack_channel, env_code_name, service_versions_list):

    """
    Retrieve required information from a image in task_defintion and put them into a predefined list.
    :param session:
    :param region_name:
    :param image:
    :return:
    """

    # getting ecs service version and name
    version_output = image['taskDefinition']['containerDefinitions'][0]['image']
    version_parsed = version_output.split("/")[-1]
    service_dot_index = version_parsed.find(':')

    service_version_prefix = version_parsed[0:service_dot_index]
    service_version_ending = version_parsed[(service_dot_index + 1):]

    # detailed ecs service
    team_service_definition = image['taskDefinition']['family']

    # this section of boto3 code slows down jarvis significantly
    # because it calls on cloudformation describe_stack for every microservices
    service_stack_name = re.split('-[A-Za-z]*Task-', team_service_definition)[0]
    # print(service_stack_name)
    cf_client = session.client("cloudformation", region_name=region_name)
    try:
        stack = cf_client.describe_stacks(StackName=service_stack_name)
    except Exception as e:
        print(('Error: {0}. No stack found for {0}'.format(e, service_stack_name)))
    build_date = ""

    for tag in stack['Stacks'][0]['Tags']:
        if tag['Key'] == 'bitbucket-build-date':
            build_date = tag['Value']
            break

    # version_parsed, team_service_name, region_name
    if len(version_output) > 1:
        c_service = {"version": service_version_ending,
                     "servicename": service_version_prefix,
                     "service_definition": team_service_definition,
                     "regionname": region_name,
                     "slackchannel": slack_channel,
                     "environment_code_name": env_code_name,
                     "build_date": build_date}
        service_versions_list.append(c_service)

    return service_versions_list


def get_bb_credential():
    try:
        ssm_client = boto3.client('ssm')
        bb_api_key=ssm_client.get_parameter(Name = "JARVIS.BB_API_KEY")['Parameter']['Value']
        bb_api_secret=ssm_client.get_parameter(Name="JARVIS.BB_API_SECRET", WithDecryption=True)['Parameter']['Value']

    except Exception as e:
        print("Error access aws ssm service: " + " (" + str(e) + ")")

    token_url = 'https://bitbucket.org/site/oauth2/access_token'
    data = {'grant_type': 'client_credentials', 'client_id': bb_api_key,
            'client_secret': bb_api_secret}
    access_token = requests.post(token_url, data=data).json()
    api_token = access_token['access_token']

    return api_token

def compare_bb_commit_parents(repo_name,commit_hash, compare_hash):
    """
    provide a commit hash and get it's parents in bitbucket
    :param commit_hash:
    :return:
    """
    api_token = get_bb_credential()
    bb_api_url="https://api.bitbucket.org/2.0/repositories/signiant/{0}/commit/{1}".format(repo_name, commit_hash)
    headers = dict()
    headers['Authorization'] = "Bearer {0}".format(api_token)
    headers['Content-Type'] = 'application/json'
    api_response = requests.get(bb_api_url, headers=headers)

    if api_response.status_code == 200:
        api_response = api_response.json()
        for parent in api_response['parents']:
            if parent['hash'][0:7] == compare_hash:
                return True
        else:
            return False
    else:
        # if api to specific repo cannot be verified set it to false at moment
        return False


def compare_environment(team_env, master_env):
    """
    compare the versions replace compare_environment
    Return types
    1 - Matches Master
    2 - Does not match master. Master is ahead(red)
    3 - branch is ahead (yellow)
    :param team_env:
    :param master_env:
    :return:
    """

    result = 0
    print("here")
    team_hash = team_env['bb_hash']
    master_hash = master_env['bb_hash']
    service_name = team_env['servicename']
    print(service_name)
    # team_branch_name = team_env['version'].replace('_','-').split('-')[1:-1]
    # master_branch_name = master_env['version'].replace('_','-').split('-')[1:-1]

    # replace signiant-installer-service dash to underscore
    # if there are more name changes in the future a seperate functions can be created
    if team_hash == "None" or master_hash == "None":
        result = 2
    else:
        if len(team_hash) == 7 and len(master_hash) == 7:
            if team_hash == master_hash:
                # if commit hash match result (green)
                result = 1
            else:
                # compare hash parents
                if compare_bb_commit_parents(service_name, team_hash, master_hash):
                    result = 1
                else:
                    # if build date does not exist for either or both team/master service (red)
                    result = 2
        else:
            # all other scenarios
            result = 2

    logging.debug("Bitbucket comparing %s and %s result is %s" % (team_hash, master_hash, result))
    return result


def finalize_service_name(service_name, service_def, environment_code_name):
    result = []

    def_name_mod = service_def.lower().replace("-", "+").replace("_", "+")
    service_name_mod = service_name.lower().replace("-", "+").replace("_", "+")

    def_name_list = def_name_mod.split("+")
    service_name_list = service_name_mod.split("+")

    for sname in service_name_list:
        if sname in def_name_list:
            def_name_list.remove(sname)

    if environment_code_name:
        if environment_code_name in def_name_list:
            def_name_list.remove(environment_code_name)
            result.append(service_name)
    return result


def build_compare_words(lookup, compareto, jenkin_build_terms):
    """
    :param lookup:
    :param compareto:
    :param jenkin_build_terms:
    :return:
    """
    result = False

    if compareto:
        if "-" in compareto:
            compareto = compareto.replace("-", "_")
        if " " in compareto:
            compareto = compareto.replace(" ", "_")
        compareto = compareto.lower().split("_")
    else:
        compareto = []
    if lookup:
        if "-" in lookup:
            lookup = lookup.replace("-", "_")
        if " " in lookup:
            lookup = lookup.replace(" ", "_")
        lookup = lookup.lower().split("_")
    else:
        lookup = []
    # aggregate unique values in the two lists
    res = list(set(compareto) ^ set(lookup))

    # if symmetric difference is 2
    if len(res) == 2 and jenkin_build_terms[0] in res and jenkin_build_terms[2] in res:
        result = True
    elif len(res) == 1 and (jenkin_build_terms[0] in res or jenkin_build_terms[1] in res):
        result = True
    return result


def get_build_url(service_name, bb_hash):
    """
    compare the service name to links in the superjenkins_data
    set the build_url when a url contains words matching the lookup service name
    :param cached_array: all the data from super jenkin
    :param lookup_word: the service keywords a string such as "telemeoldtry_service"
    :param service_definition: get service defnitio to find the stack name
    :param service_version: the version string in the format of "master-8"
    :param jenkins_tags: a list in the format [u'master', u'trunk', u'build']
    :return:
    """
    the_url = ""

    the_url = "https://bitbucket.org/signiant/{0}/commits/{1}".format(service_name,bb_hash)

    # build up url for slack display
    if the_url:
        final_url = str(the_url) + " | ver: " + str(bb_hash)
        final_url = "<" + final_url + ">"
    else:
        # build url corresponding to service was not found
        final_url = "ver: " + str(bb_hash)

    return final_url


def comp_strings_charnum(string1, string2):
    """
    strip all non alphanumeric chars and compare strings
    :param string1:
    :param string2:
    :return:
    """
    comp_string1 = re.sub('[^0-9a-zA-Z]+', '', string1)
    comp_string2 = re.sub('[^0-9a-zA-Z]+', '', string2)
    result = comp_string1 == comp_string2
    return result


def lambda_compare_master_team(t_array, m_array):
    """
    compare master to teams
    :param t_array: the version of services in team branch
    :param m_array: the version of services in prod branch
    :param cached_array: jenkin_data from superjenkin
    :param jenkins_build_tags:
    :param excluded_services:
    :return:
    """
    compared_array = {}
    ecs_data = []
    print("check")
    print(t_array)
    print(m_array)
    for service_name in m_array:
        if service_name in t_array:
            amatch = compare_environment(t_array[service_name], m_array[service_name])

            print("finish compare {0}".format(amatch))
            # if the match is of type 2 where environment/service is not matching prod master
            #   and not a dev branch get the build
            if amatch == 2:
                print(m_array[service_name])
                ecs_master_version_entry = get_build_url( m_array[service_name]['servicename'],
                                                          m_array[service_name]['bb_hash'])

            else:
                ecs_master_version_entry = "ver: " + m_array[service_name]['bb_hash']

            ecs_team_version_entry = "ver: " + t_array[service_name]['bb_hash']

            print("add together?")
            ecs_data.append({"master_env": m_array[service_name]['lambda_name'],
                             "master_version": ecs_master_version_entry,
                             "master_updateddate": "",
                             "team_env": t_array[service_name]['lambda_name'],
                             "team_version": ecs_team_version_entry,
                             "team_updateddate": "",
                             "Match": amatch, "mastername": 'prod',
                             "regionname": t_array[service_name]['regionname'],
                             "slackchannel": "",
                             "pluginname": "lambda"
                             })
        else:
            ecs_master_version_entry = "ver: " + m_array[service_name]['bb_hash']

            ecs_data.append({"master_env": m_array[service_name]['lambda_name'],
                             "master_version": ecs_master_version_entry,
                             "master_updateddate": "",
                             "team_env": "Missing",
                             "team_version": "version not avaliable",
                             "team_updateddate": "",
                             "Match": 2, "mastername": 'prod',
                             "regionname": "place_holder_version",
                             "slackchannel": "",
                             "pluginname": "lambda"
                             })
        compared_array.update({'lambda service': ecs_data})

    print("compare done")
    return compared_array


# main ecs plugin function
def main_lambda_check_versions(master_array, team_array):
    print("team array")
    print(team_array['environment_code_name'])
    m_region_name = master_array['region_name']
    m_role_arn = master_array['RoleArn']
    m_env = master_array['environment_code_name']

    t_region_name = team_array['region_name']
    t_role_arn = team_array['RoleArn']
    t_env = team_array['environment_code_name']

    # following var are arbitrary can be from team or master. since they are universal when retrieved from aws config
    service_exclude_list =team_array['service_exclude_list']
    service_map_list = team_array['service_mapping_list']

    master_plugin_data = lambda_check_versions(m_region_name,m_role_arn,m_env, service_exclude_list,service_map_list)

    if master_plugin_data:

        team_plugin_data = lambda_check_versions(t_region_name, t_role_arn,t_env,service_exclude_list,service_map_list )

        print('master_plugin_data')
        print(master_plugin_data)
        print('team_plugin_data')
        print(team_plugin_data)
        compared_data = lambda_compare_master_team(team_plugin_data,master_plugin_data)

    return compared_data
