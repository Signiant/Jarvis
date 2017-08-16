import boto3, json, imp, pprint
from botocore.exceptions import ClientError
import logging
import xml.etree.ElementTree as ET

appversions = []


def log(message):
    print id() + ": " + message

def id():
    return "s3"


# retrieve json data from super jenkins for build urls
def read_s3_data(my_bucket, my_key, role_arn):

    result = []
    temp_dir = dict()
    previous_item_tag = None
    os_name = None

    try:

        mysession = get_new_boto_session(role_arn)

        s3 = mysession.resource('s3')
        logging.info("Retrieving file from s3 bucket data")

        obj = s3.Object(my_bucket, my_key)
        json_body = obj.get()['Body'].read()

        json_body = ("").join(json_body.split('\n\t\t'))

        tree = ET.fromstring(json_body)

        for item in tree.iter():
            #getting values from xml string object
            if item.tag == "version":
                os_name = previous_item_tag
                if item.text != '\n':
                    temp_dir[item.tag] = item.text
            if item.tag == "file":
                temp_dir[item.tag] = item.text
                temp_dir["os"] = os_name
                result.append(temp_dir)
                temp_dir = dict()

            previous_item_tag = item.tag

    except Exception, e:
        print "Error in retrieving and creating json from s3 ==> " + str(e)

    return result


def get_new_boto_session(role_arn):
    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None
    sts_client = boto3.client('sts')
    if role_arn:
        assumedRole = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="AssumedRole")
        awsKeyId = assumedRole['Credentials']['AccessKeyId']
        awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
        awsSessionToken = assumedRole['Credentials']['SessionToken']
    mysession = boto3.session.Session(aws_access_key_id=awsKeyId,
                                      aws_secret_access_key=awsSecretKey,
                                      aws_session_token=awsSessionToken)
    return mysession


# eb do boto call and retrieve data
def get_s3_data(the_array):

    store_bucket_result = []
    store_result = dict()
    temp_dir = []
    page_iterator = None


    if the_array['RoleArn']:
        mysession = get_new_boto_session(the_array['RoleArn'])
    else:
        mysession = get_new_boto_session(None)

    s3 = mysession.client("s3")

    for bucket in the_array['Directory_List']:
        try:
            paginator = s3.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(Bucket=bucket['bucketname'])

            for page in page_iterator:
                page_contents = page['Contents']

                for directory in bucket['Directories']:

                    lookup_directory = filter(None, directory['Directory'].split('/'))

                    if directory['compare_type'] == 'check_xml':
                        for item in page_contents:
                            lookup_item = filter(None, item[u'Key'].split('/'))

                            if lookup_directory and lookup_item:
                                if lookup_directory[0] in lookup_item[0] and len(lookup_item) == len(lookup_directory) + 1:

                                    if ".xml" in lookup_item[1]:
                                        for the_file in directory['file_list']:
                                            if item[u'Key'].split("/")[-1] in the_file['filename']:
                                                s3_data_for_key = read_s3_data(bucket['bucketname'],item[u'Key'], the_array['RoleArn'])
                                                temp_dir.append({item[u'Key'].split("/")[-1]:s3_data_for_key,"filekey":the_file["filekey"]})
                                                break

                            elif len(lookup_directory) == 0 and lookup_item:
                                if len(lookup_item) == 1:
                                    # add values to be associated with each directory
                                    if directory['compare_type'] == 'check_xml':
                                        if ".xml" in lookup_item[0]:
                                            for the_file in directory['file_list']:
                                                if item[u'Key'].split("/")[-1] in the_file['filename']:
                                                    s3_data_for_key = read_s3_data(bucket['bucketname'], item[u'Key'],
                                                                                   the_array['RoleArn'])
                                                    temp_dir.append({item[u'Key'].split("/")[-1]: s3_data_for_key,
                                                                     "filekey": the_file["filekey"]})
                                                    break

                    if temp_dir:
                        store_result[directory['Directory']] = temp_dir
                        temp_dir = []

            if store_result:
                store_bucket_result.append({bucket['bucketname']: store_result})
                store_result = dict()

        except Exception, e:
            print "Error in doing call for bucket " + str(e)
    return store_bucket_result


def compare_file_version(master_arr_comp, team_arr_comp):
    if master_arr_comp["version"] == team_arr_comp["version"]:
        return 1
    else:
        return 2


def get_team_name(m_data):
    for data in m_data['Directory_List']:
        for directory in data:
            return data['team_name']


def s3_compare_master_team(m_array, tkey, team_name):

    s3_data = []

    for m_item in m_array:
        for m_stuff in m_array[m_item]:
                for t_item in tkey:
                    for t_stuff in tkey[t_item]:
                        print "*************************"
                        print str(m_item)+"/"+str(m_stuff)
                        print t_item+"/"+str(t_stuff)
                        print "*************************"

                        if m_stuff == t_stuff:

                            if "media_shuttle_standalone" in m_stuff:
                                print "cool"

                            master_ver = []
                            team_ver = []
                            amatch = None
                            amatch_status = True

                            for m_file in m_array[m_item][m_stuff]:
                                for m_system in m_file:
                                    if m_system is not "filekey":
                                        for the_m in m_file[m_system]:

                                            for t_file in tkey[t_item][t_stuff]:
                                                for t_system in t_file:
                                                    if t_system is not "filekey":
                                                        for the_t in t_file[t_system]:

                                                            if "media-shuttle-standalone-linux-info" in m_system:
                                                                print "cool"

                                                            if the_m["os"] == the_t["os"] and m_file['filekey'] == t_file['filekey']:
                                                                amatch = compare_file_version(the_m,the_t)

                                                                current_m_file_name = "\n\n"+str(m_system).split(".")[0] +"\n"+str(the_m['version'])
                                                                current_t_file_name = "\n\n"+str(t_system).split(".")[0] +"\n"+ str(the_t['version'])

                                                                if amatch == 2:
                                                                    amatch_status = False

                                                                if len(master_ver) > 0 and len(team_ver) > 0:
                                                                    if current_m_file_name not in master_ver and current_m_file_name not in team_ver:
                                                                        master_ver.append(current_m_file_name)
                                                                        team_ver.append(current_t_file_name)
                                                                else:
                                                                    master_ver.append(current_m_file_name)
                                                                    team_ver.append(current_t_file_name)

                                                                if amatch_status == False:
                                                                    amatch = 2
                                                                else:
                                                                    amatch = 1

                            if m_stuff == '':
                                m_stuff = str(m_item)

                            if t_stuff == '':
                                t_stuff = str(t_item)

                            s3_data.append({"master_env": m_stuff,
                                            "master_version": "\n"+("\n").join(master_ver),
                                            "master_updateddate": "",
                                            "team_env": t_stuff,
                                            "team_version": "\n"+("\n").join(team_ver),
                                            "team_updateddate": "",
                                            "Match": amatch, "mastername": team_name,
                                            "regionname": "",
                                            "pluginname": "s3"
                                            })

    return s3_data if s3_data else None


# main eb plugin function
def main_eb_check_versions(master_array, team_array):

    master_plugin_data = get_s3_data(master_array)
    compared_data = []

    #get the team name associated with master data set
    team_name = get_team_name(master_array)

    print "***************************************"
    pprint.pprint(master_plugin_data)
    print "***************************************"

    if master_plugin_data:
        team_plugin_data = get_s3_data(team_array)

        print "***************************************"
        pprint.pprint(team_plugin_data)
        print "***************************************"

        for m_plugin_data in master_plugin_data:
            for t_plugin_data in team_plugin_data:
                s3_compare_result = s3_compare_master_team(m_plugin_data, t_plugin_data, team_name)
                if s3_compare_result:
                    if compared_data:
                        compared_data = compared_data + s3_compare_result
                    else:
                        compared_data = s3_compare_result

    pprint.pprint(compared_data)

    return {'s3 Artifact': compared_data}


