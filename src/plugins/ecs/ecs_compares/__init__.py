import boto3
import logging
import re
import time
import requests


# get ecs data from boto call
def ecs_check_versions(profile_name, region_name, cluster_name, slack_channel, env_code_name, role_arn):

    service_versions = []
    cluster_list = []
    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None

    # get list of clusters
    if type(cluster_name) == list:
        for c_items in cluster_name:
            cluster_list.append(c_items)
    else:
        cluster_list.append(cluster_name)

    for cluster in cluster_list:
        try:
            sts_client = boto3.client('sts')
            if role_arn:
                assumedRole = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="AssumedRole")
                awsKeyId = assumedRole['Credentials']['AccessKeyId']
                awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
                awsSessionToken = assumedRole['Credentials']['SessionToken']
            session = boto3.session.Session(aws_access_key_id=awsKeyId, aws_secret_access_key=awsSecretKey, aws_session_token=awsSessionToken)
            client = session.client("ecs", region_name=region_name)
            if client:
                service_paginator = client.get_paginator('list_services')
                service_iterator = service_paginator.paginate(cluster=cluster)
        except Exception as e:
            print(("Error obtaining list of ECS services for " + cluster + " (" + str(e) + ")"))
        except KeyError as e:
            print(("Key " + e + "not found"))

        try:
            for service in service_iterator:
                # Get the service info for each batch
                services_descriptions = client.describe_services(cluster=cluster, services=service['serviceArns'])
                for service_desc in services_descriptions['services']:
                    image = client.describe_task_definition(taskDefinition=service_desc['taskDefinition'])

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
                        continue
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
                        service_versions.append(c_service)

        except Exception as e:
            print(("Error obtaining paginated services for " + str(cluster) + " (" + str(e) + ")"))

    return service_versions


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
    api_response = requests.get(bb_api_url, headers=headers).json()

    for parent in api_response['parents']:
        if parent['hash'][0:7] == compare_hash:
            return True
    else:
        return False


def compare_build_time(team_env, master_env):
    """
    compare build time of two environment when team_env['build_date'] and master_env['build_date'] exist
    :param team_env:
    :param master_env:
    :return:
    """
    team_time = time.strptime(team_env['build_date'], "%Y-%m-%dT%H:%M:%S+00:00")
    master_time = time.strptime(master_env['build_date'], "%Y-%m-%dT%H:%M:%S+00:00")
    if team_time > master_time:
        # if team branch commit time newer than master commit time (yellow)
        result = 3
    else:
        # master commit time is newer than team branch commit time (red)
        result = 2

    return result


def jenkins_compare_environment(team_env, master_env, jenkins_build_terms):
    # compare the versions
    """""
    Return types
    1 - Matches Master
    2 - Does not match master
    3 - branch
    """""
    result = 0

    if jenkins_build_terms[0] in master_env or jenkins_build_terms[1] in master_env:
        if team_env == master_env:
            result = 1
        else:
            team_deploy_num=int(team_env.split('-')[-1])
            prod_deploy_num=int(master_env.split('-')[-1])
            if (jenkins_build_terms[0] in team_env or jenkins_build_terms[1] in team_env) and team_deploy_num > prod_deploy_num:
                # if team deploy number in jenkin > prod deploy number (yellow)
                result = 3
            else:
                result = 2

    logging.debug("Jenkins comparing %s and %s result is %s" % (team_env, master_env, result))
    return result


def compare_environment(team_env, master_env, jenkins_build_terms ):
    """
    compare the versions replace compare_environment
    Return types
    1 - Matches Master
    2 - Does not match master. Master is ahead(red)
    3 - branch is ahead (yellow)
    :param team_env:
    :param master_env:
    :param jenkins_build_terms:
    :return:
    """

    result = 0
    team_hash = team_env['version'].split('-')[-1]
    master_hash = master_env['version'].split('-')[-1]
    service_name = team_env['servicename'].replace('_','-')
    team_branch_name = team_env['version'].replace('_','-').split('-')[1:-1]
    master_branch_name = master_env['version'].replace('_','-').split('-')[1:-1]

    if len(team_hash) == 7 and len(master_hash) == 7:
        if team_hash == master_hash:
            # if commit hash match result (green)
            result = 1
        elif len(team_branch_name) > 0:
            # if a sub team branch exist and is currently deployed in the dev environment (yellow)
            result = 3
        else:
            if team_env['build_date'] and master_env['build_date']:
                # if build dates are available for both sections
                if compare_bb_commit_parents(service_name, team_hash, master_hash):
                    result = 1
                else:
                    # compare build time between two environment
                    result = compare_build_time(team_env, master_env)
            else:
                # if build date does not exist for either or both team/master service (red)
                result = 2
    elif (len(team_hash) == 7) ^ (len(master_hash) == 7):
        # if one is jenkin build number or other one is bitbucket hash (red) but not both
        result = 2

    elif 'master' in master_env['version'] and 'master' in team_env['version']:
        # if hash len is not 7 for both master and team
        # that means jenkin build master on both prod and dev comparison environment (not bitbucket way)
        result = jenkins_compare_environment(team_env['version'], master_env['version'], jenkins_build_terms)
    else:
        # all other scenarios
        result = 2

    logging.debug("Bitbucket comparing %s and %s result is %s" % (team_env['version'], master_env['version'], result))
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


def get_build_url(cached_array, lookup_word, service_definition, service_version,  jenkins_tags):
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

    service_stack_name = service_definition.split('-Task-')[0]
    cloudformation = boto3.resource('cloudformation')
    stack = cloudformation.Stack(service_stack_name)

    for tag in stack.tags:
        if tag['Key'] == 'jenkins-build-url':
            the_url = tag['Value']
        elif tag['Key'] == 'bitbucket-build-url' and len(tag['Value'])>1:
            parse_bb_val=tag['Value'].split('/')
            repo_name = parse_bb_val[0]
            pip_num=parse_bb_val[1]
            the_url = "https://bitbucket.org/signiant/{0}/addon/pipelines/home#!/results/{1}".format(repo_name,pip_num)

    # backward compatible to use previous way to get the jenkin build url
    if not the_url:
        for the_names in cached_array:
            if build_compare_words(lookup_word, the_names['name'], jenkins_tags):
                the_url = the_names['url']
        symbols_array = [".", "_", "-"]
        build_num = []
        # extract the build number from version
        for symb in symbols_array:
            if symb in service_version:
                build_num = service_version.split(symb)
                break

    # build up url for slack display
    if the_url:
        final_url = str(the_url) + " | ver: " + str(service_version)
        final_url = "<" + final_url + ">"
    else:
        # build url corresponding to service was not found
        final_url = "ver: " + str(service_version)

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


def ecs_compare_master_team(tkey, m_array, cached_array, jenkins_build_tags, excluded_services=None):
    """
    compare master to teams
    :param tkey:
    :param m_array: the version of services in prod branch
    :param cached_array: jenkin_data from superjenkin
    :param jenkins_build_tags:
    :param excluded_services:
    :return:
    """
    compared_array = {}
    ecs_data = []

    # this array will contain all services not found in team array not holding master data
    not_in_team_array = []
    for m_items in m_array:
        for m_things in m_array[m_items]:
            not_in_team_array.append(m_things)

    for eachmaster in m_array:
        for m_data in m_array[eachmaster]:

            for t_array in tkey:
                if t_array['servicename'].replace("_", "-") == m_data['servicename'].replace("_", "-"):

                    logging.debug("Printing comparison of service_definition")
                    logging.debug(t_array['service_definition'] + " == " + m_data['service_definition'])

                    # check if service_name is on excluded services list
                    do_not_exclude_service = True
                    for ex_service in excluded_services:
                        if comp_strings_charnum(ex_service, t_array['servicename']):
                            do_not_exclude_service = False

                    if do_not_exclude_service:

                        the_team_service_name = finalize_service_name(t_array['servicename'],
                                                                      t_array['service_definition'],
                                                                      t_array['environment_code_name'])

                        the_master_service_name = finalize_service_name(m_data['servicename'],
                                                                        m_data['service_definition'],
                                                                        m_data['environment_code_name'])

                        if the_team_service_name and the_master_service_name:
                            logging.debug(the_team_service_name[0] + " == " + the_master_service_name[0] + "\n\n")

                            if the_team_service_name[0].replace("_", "-") == the_master_service_name[0].replace("_", "-"):
                                if m_data in not_in_team_array:
                                    not_in_team_array.remove(m_data)

                                #############################################
                                # print(t_array, " compare ", m_data)
                                # print(t_array['version'], " compare ", m_data['version'])

                                amatch = compare_environment(t_array, m_data, jenkins_build_tags)
                                logging.debug(t_array['version'] + " === " + m_data['version'] + "\n")

                                # if the match is of type 2 where environment/service is not matching prod master
                                #   and not a dev branch get the build
                                if amatch == 2:
                                    if len(the_master_service_name) == 2:
                                        ecs_master_version_entry = get_build_url(cached_array, the_master_service_name[1], m_data['service_definition'],
                                                                                 m_data['version'], jenkins_build_tags)
                                    elif len(the_master_service_name) == 1:
                                        ecs_master_version_entry = get_build_url(cached_array, the_master_service_name[0], m_data['service_definition'],
                                                                                 m_data['version'], jenkins_build_tags)
                                else:
                                    ecs_master_version_entry = "ver: " + m_data['version']

                                ecs_team_version_entry = "ver: " + t_array['version']

                                if amatch == 0:
                                    print(("match is zero ", t_array['servicename'], " task_def: ", t_array[
                                        'service_definition'], " => ", the_team_service_name))

                                # see if a slackchannel is available for team
                                if ('slackchannel' in t_array) == False:
                                    t_array['slackchannel'] = ""

                                ecs_data.append({"master_env": the_master_service_name[0],
                                                 "master_version": ecs_master_version_entry,
                                                 "master_updateddate": "",
                                                 "team_env": the_team_service_name[0],
                                                 "team_version": ecs_team_version_entry,
                                                 "team_updateddate": "",
                                                 "Match": amatch, "mastername": eachmaster,
                                                 "regionname": t_array['regionname'],
                                                 "slackchannel": t_array['slackchannel'],
                                                 "pluginname": "ecs"
                                                 })
                    break

    # add all master services not found to ecs data output
    if not_in_team_array:
        for m_data in not_in_team_array:

            # check if service_name is on excluded services list
            do_not_exclude_service = True
            for ex_service in excluded_services:
                if comp_strings_charnum(ex_service, m_data['servicename']):
                    do_not_exclude_service = False

            if do_not_exclude_service:
                the_master_service_name = finalize_service_name(m_data['servicename'],
                                                                m_data['service_definition'],
                                                                m_data['environment_code_name'])

                if the_master_service_name:
                    # if the match is of type 2 where environment/service is not matching prod master
                    #   and not a dev branch get the build

                    if len(the_master_service_name) == 2:
                        ecs_master_version_entry = get_build_url(cached_array, the_master_service_name[1], m_data['service_definition'],
                                                                 m_data['version'],
                                                                 jenkins_build_tags)
                    elif len(the_master_service_name) == 1:
                        ecs_master_version_entry = get_build_url(cached_array, the_master_service_name[0], m_data['service_definition'],
                                                                 m_data['version'],
                                                                 jenkins_build_tags)
                    ecs_data.append({"master_env": the_master_service_name[0],
                                     "master_version": ecs_master_version_entry,
                                     "master_updateddate": "",
                                     "team_env": "Service Not Found",
                                     "team_version": "",
                                     "team_updateddate": "",
                                     "Match": 2, "mastername": m_data['environment_code_name'],
                                     "regionname": "",
                                     "pluginname": "ecs"})

    # remove duplicates in ecs_data list
    ecs_data_temp = []
    for ecs_service in ecs_data:
        if ecs_service not in ecs_data_temp:
            ecs_data_temp.append(ecs_service)
    ecs_data = ecs_data_temp

    compared_array.update({'ecs service': ecs_data})
    return compared_array


# main ecs plugin function
def main_ecs_check_versions(master_array, team_array, jenkins_build_tags, superjenkins_data, team_exclusion_list):
    masterdata = dict()

    master_plugin_data = ecs_check_versions(master_array['account'],
                                            master_array['region_name'],
                                            master_array['cluster_name'],
                                            "",
                                            master_array['environment_code_name'],
                                            master_array['RoleArn'])

    if master_plugin_data:
        masterdata[master_array['environment_code_name']] = master_plugin_data

        team_plugin_data = ecs_check_versions(team_array['account'], team_array['region_name'],
                                              team_array['cluster_name'], "",
                                              team_array['environment_code_name'],
                                              team_array['RoleArn'])

        compared_data = ecs_compare_master_team(team_plugin_data,
                                                masterdata,
                                                superjenkins_data,
                                                jenkins_build_tags,
                                                team_exclusion_list)
    return compared_data
