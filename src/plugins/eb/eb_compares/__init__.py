import boto3
import logging
import requests

appversions = []


def log(message):
    print((id() + ": " + message))


def id():
    return "eb"


def get_new_boto_session(role_arn):

    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None

    sts_client = boto3.client('sts')
    if role_arn:
        assumedRole = sts_client.assume_role(RoleArn=role_arn,RoleSessionName="AssumedRole")
        awsKeyId = assumedRole['Credentials']['AccessKeyId']
        awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
        awsSessionToken = assumedRole['Credentials']['SessionToken']

    mysession = boto3.session.Session(aws_access_key_id=awsKeyId,
                                      aws_secret_access_key=awsSecretKey,
                                      aws_session_token=awsSessionToken)
    return mysession


# eb do boto call and retrieve data
def eb_check_versions(region_name, env_array, role_arn, team_name):
    appversions = []

    for areas in env_array:
        mysession = get_new_boto_session(role_arn)
        client = mysession.client("elasticbeanstalk", region_name=region_name)
        response = client.describe_environments(
            IncludeDeleted=False,
        )

        for env in response['Environments']:
            if env['ApplicationName'] == areas:

                c_version = env['VersionLabel']
                c_app = env['ApplicationName']
                c_env = env['EnvironmentName']
                c_solstack = env['SolutionStackName']
                c_health = env['Health']
                date_updated = env['DateUpdated']

                # retrieve tags from eb environments
                eb_descr_response = client.describe_environments(EnvironmentNames=[c_env])
                environment_arn = eb_descr_response['Environments'][0]['EnvironmentArn']
                eb_tag_result = client.list_tags_for_resource(ResourceArn=environment_arn)
                c_tag = eb_tag_result['ResourceTags']
                # set app version
                c_appversion = {('app'): c_app, ('version'): c_version, ('environmentname'): c_env,
                                ('solutionstack'): c_solstack, ('health'): c_health, ('dateupdated'): date_updated,
                                ('regionname'): region_name, ('team_name'):team_name, ('tags'):c_tag}

                if areas in c_app:
                    logging.debug("MATCH: version label is %s app is %s environment is %s\n areas is %s checking app %s\n\n"%(
                        c_version,c_app,c_env, areas,c_app))
                else:
                    logging.debug("version label is %s app is %s environment is %s\n areas is %s checking app %s" % (
                    c_version, c_app, c_env, areas, c_app))

                # add the corresponding build name key term for each eb environment
                c_appversion.update({('build_master_tag'): env_array[areas]['build_master_tag']})

                current_dns_name = env_array[areas]['dns_name']
                current_zone_id = env_array[areas]['zone_id']

                if current_dns_name != "" and current_zone_id != "":
                    # if the environments dns and zone information are in another account than start new boto session for
                    # the new account associated with this environment
                    if env_array[areas].get('alternate_role_arn'):
                        mysession = get_new_boto_session(env_array[areas]['alternate_role_arn'])

                    try:
                        eb_route53_session = mysession.client('route53')
                        records = eb_route53_session.list_resource_record_sets(HostedZoneId=current_zone_id,
                                                                               StartRecordName=current_dns_name,
                                                                               StartRecordType='A')
                        if 'AliasTarget' in records['ResourceRecordSets'][0]:
                            activeLoadBalancer = records['ResourceRecordSets'][0]['AliasTarget']['DNSName']
                            ga_enabled = False
                        elif 'ResourceRecords' in records['ResourceRecordSets'][0]:
                            ip_list = [records['ResourceRecordSets'][0]['ResourceRecords'][0]['Value'], records['ResourceRecordSets'][0]['ResourceRecords'][1]['Value']]
                            endpoint_load_balancer_arn = get_global_accelerators(ip_list)
                            if not endpoint_load_balancer_arn:
                                continue
                            ga_enabled = True
                            try:
                                eb_elb_session = mysession.client('elbv2')
                                load_balancer = eb_elb_session.describe_load_balancers(
                                    LoadBalancerArns=[endpoint_load_balancer_arn])
                                load_balancer_dns = load_balancer['LoadBalancers'][0]['DNSName']
                            except Exception as e:
                                print(("elbv2 call error " + str(e)))
                                print("error end")

                    except Exception as e:
                        print(("Route53 call error "+str(e)))
                        print("error end")

                    if ga_enabled:
                        if load_balancer_dns:
                            if env['EndpointURL'].lower() in load_balancer_dns.lower():
                                if env['Health'] == "Green" or env['Health'] == "Yellow" or env['Health'] == "Red":
                                    appversions.append(c_appversion)
                    else:
                        if activeLoadBalancer:
                            if env['EndpointURL'].lower() in activeLoadBalancer.lower():
                                if env['Health'] == "Green" or env['Health'] == "Yellow" or env['Health'] == "Red":
                                    appversions.append(c_appversion)


    return appversions


def get_global_accelerators(ip_list):
    """find corresponding global accelerator end points id when given two IP addresses as list from Route53 record set
    no pagination at this point"""
    matching_accelerator = ""
    try:
        my_session = boto3.session.Session(region_name="us-west-2")
        globalaccelerator = my_session.client('globalaccelerator')
        accelerator_list = globalaccelerator.list_accelerators()
    except Exception as e:
        print("Could not connect to AWS Global Accelerator: %s" % str(e))
    try:
        for accelerator in accelerator_list['Accelerators']:
            if set(accelerator['IpSets'][0]['IpAddresses']) == set(ip_list):
                matching_accelerator = accelerator
                break
    except:
        print("Error getting details from AWS Global Accelerator")

    if matching_accelerator:
        accelerator_arn = matching_accelerator['AcceleratorArn']
        try:
            listeners = globalaccelerator.list_listeners(AcceleratorArn=accelerator_arn)
            listener_arn = listeners['Listeners'][0]['ListenerArn']
            endpoint_groups = globalaccelerator.list_endpoint_groups(ListenerArn=listener_arn)
        except Exception as e:
            print("Could not connect to AWS Global Accelerator: %s" % str(e))
            return "error"

        try:
            for endpoint_group in endpoint_groups['EndpointGroups']:
                if endpoint_group['TrafficDialPercentage'] == 100:
                    for endpoint in endpoint_group['EndpointDescriptions']:
                        if endpoint['Weight'] > 0:
                            live_load_balancer_arn = endpoint['EndpointId']
                            return live_load_balancer_arn
        except:
            print("Missing endpoint gropus")

    return False




# version print out for eb environments
def get_version_output_string(thestring):

    team_dot_index = thestring.find('.')
    team_version_ending = thestring[team_dot_index:]
    version_isolate = team_version_ending.split('.')

    if version_isolate[-2].isdigit():
        e_str = ('.').join(version_isolate[:-1])
    elif version_isolate[-3].isdigit():
        e_str = ('.').join(version_isolate[:-2])
    else:
        e_str = ('.').join(version_isolate[:-1])

    return e_str[1:]


# extract the second part of service name to compare
def get_service_name_ending(thestring):
    slash_index = thestring.find('/')
    thestring = thestring[(slash_index+1):]
    slash_index = thestring.find('-')
    thestring = thestring[(slash_index + 1):]
    return thestring.replace('.json',"")


# Main comparing function
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


def compare_environment(team_version, master_version):

    """""
    Return types
    1 - Matches Master (green)
    2 - Does not match master, but branch have 'master' in it's name instead (red)
    3 - branch (yellow)
    """""

    # Assume branch, unless we find master
    result = 3

    team_hash = team_version.split('.')[-2]
    master_hash = master_version.split('.')[-2]
    service_name = master_version.split('.')[0]
    team_branch_name = team_version.split('.')[1]
    master_branch_name = master_version.split('.')[1]

    if len(team_hash) == 7 and len(master_hash) == 7:
        if team_hash == master_hash:
            # same hash same build
            result = 1
        else:
            if compare_bb_commit_parents(service_name, team_hash, master_hash):
                # if master and team's hashes belong to the same commit parents
                result = 1
            else:
                # hashes are different
                if 'master' in team_branch_name:
                    # if master is in team name
                    result = 2

    elif (len(team_hash) == 7) ^ (len(master_hash) == 7):
        # if one is jenkin build number or other one is bitbucket hash (red) but not both
        result = 3
    else:
        # all other scenarios
        result = 3

    # print " MATCH IS: "+team_env +" == " + master_env+" ==> "+str(result)

    print(("comparing %s and %s result is %s"% (team_version, master_version, result)))
    return result


def does_key_exist(thearray,thestring):
    if thearray[thestring]:
        return thearray[thestring]
    else:
        return ""


# compress string is larger than 30 length
def shorten_input(thestring):
    if len(thestring) > 30:
        thestring = thestring[:27]+"..."
        return thestring
    else:
        return thestring


# get build url
def format_string_for_comparison(word):
    if "-" in word:
        word = word.replace("-","_")
    if " " in word:
        word = word.replace(" ","_")

    word = word.lower().split("_")

    return word


def build_compare_words(lookup,compareto, j_tags):

    result = False

    compareto = format_string_for_comparison(compareto)
    lookup = format_string_for_comparison(lookup)

    res = list(set(compareto) ^ set(lookup))

    if len(res) == 2 and j_tags[0] in res and j_tags[2] in res:
        result = True
    elif len(res) == 1 and (j_tags[0] in res or j_tags[1] in res):
        result = True

    return result


def get_build_url(cached_array, lookup_word, prelim_version, j_tags, match_num, eb_tags, ismaster):

    the_url = None
    build_detail = None
    # print(cached_array)
    repo_name=""
    pip_num=0
    print("tags "+str(eb_tags))
    for env_tag in eb_tags:
        if env_tag['Key'] == 'bitbucket-name':
            repo_name = env_tag['Value']
        if env_tag['Key'] == 'bitbucket-pipe-num':
            pip_num=env_tag['Value']
    print(repo_name, pip_num)
    the_url = "https://bitbucket.org/signiant/{0}/addon/pipelines/home#!/results/{1}".format(repo_name,pip_num)
    print(the_url)
    for the_names in cached_array:
        if build_compare_words(lookup_word, the_names['name'], j_tags):
            build_detail = the_names['name']

    symbols_array = [".","_","-"]

    build_num = []
    build_detail = shorten_input(build_detail)

    for symb in symbols_array:
        if symb in prelim_version:
            build_num = prelim_version.split(symb)
            break

    if match_num == 2 and ismaster:
        if len(build_num) > 1 and the_url:
            final_url = str(the_url)+" | ver: "+str(prelim_version)
            final_url =  "build: "+ build_detail+"\n<"+final_url+ ">"
        else:
            # build url corresponding to service was not found
            final_url = "build: "+ build_detail+"\nver: "+str(prelim_version)
    else:
        final_url = "build: " + build_detail + "\nver: " + str(prelim_version)

    return final_url


def eb_compare_master_team(tkey,m_array, cached_array, jenkins_build_tags):

    compared_array = dict()
    eb_data = []

    # this array will contain all applications not found in team array not holding master data
    not_in_team_array = []
    for things in m_array:
        not_in_team_array.append(things)

    amatch = None
    for m_data in m_array:
        for t_array in tkey:
            logging.debug(t_array['regionname'] +" "+t_array['version'])

            team_dot_index = t_array['version'].find('.')
            team_version_prefix = t_array['version'][:team_dot_index]
            team_version_ending = t_array['version'][team_dot_index:]

            master_dot_index = m_data['version'].find('.')
            master_version_prefix = m_data['version'][0:master_dot_index]
            master_version_ending = m_data['version'][master_dot_index:]

            if team_version_prefix == master_version_prefix:
                # remove matched applications from not_in_team_array
                not_in_team_array.remove(m_data)

                amatch = compare_environment(t_array['version'], m_data['version'])

                prelim_master_version = get_version_output_string(m_data['version'])
                master_version_entry = get_build_url(cached_array, m_data['build_master_tag'],
                                                     prelim_master_version, jenkins_build_tags,
                                                     amatch, m_data['tags'], ismaster=True)

                prelim_team_version = get_version_output_string(t_array['version'])
                team_version_entry = get_build_url(cached_array, t_array['build_master_tag'],
                                                     prelim_team_version, jenkins_build_tags,
                                                     amatch, t_array['tags'], ismaster=False)


                print(('master ver: %s, team ver: %s, Match %s' %(master_version_entry, team_version_entry, amatch)))
                eb_data.append({"master_env":m_data['environmentname'],
                         "master_version": master_version_entry,
                         "master_updateddate":m_data['dateupdated'],
                         "team_env":t_array['environmentname'],
                         "team_version": team_version_entry,
                         "team_updateddate":t_array['dateupdated'],
                         "Match":amatch, "mastername": m_data['team_name'],
                         "regionname":t_array['regionname'],
                         "pluginname": "eb"
                        })
                break

    # add all master applications not found to eb data output
    if not_in_team_array:
        for m_data in not_in_team_array:
            prelim_master_version = get_version_output_string(m_data['version'])
            master_version_entry = get_build_url(cached_array, m_data['build_master_tag'],
                                                 prelim_master_version, jenkins_build_tags,
                                                 amatch,m_data['tags'], ismaster=True)

            print(('master ver: %s, team ver: %s, Match %s' % (master_version_entry, "", "2")))
            eb_data.append({"master_env": m_data['environmentname'],
                            "master_version": master_version_entry,
                            "master_updateddate": m_data['dateupdated'],
                            "team_env": "Environment Not Found",
                            "team_version": "",
                            "team_updateddate": "",
                            "Match": 2, "mastername": m_data['team_name'],
                            "regionname": "",
                            "pluginname": "eb"})

    compared_array.update({'eb env': eb_data})
    return compared_array


# main eb plugin function
def main_eb_check_versions(master_array, team_array, superjenkins_data, jenkins_build_tags):

    master_plugin_data = eb_check_versions(master_array['region_name'],
                                           master_array['environments'],
                                           master_array['RoleArn'],
                                           master_array['team_name'])

    if master_plugin_data:
        team_plugin_data = eb_check_versions(team_array['region_name'],
                                             team_array['environments'],
                                             team_array['RoleArn'],
                                             master_array['team_name'])

        compared_data = eb_compare_master_team(team_plugin_data, master_plugin_data, superjenkins_data, jenkins_build_tags)

    return compared_data
