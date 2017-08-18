import boto3, json, imp, pprint
from botocore.exceptions import ClientError
import logging
import xml.etree.ElementTree as ET

appversions = []


def log(message):
    print id() + ": " + message

def id():
    return "s3"


# retrieve xml data in each bucket with key
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
        #change the json data to xml fromstring
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
            #Holds the previous item tag that contains the os name
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


# retrieve s3 data for master and secondary data sets
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
                #iterate through the contents of s3 lis objects, which contains all keys in bucket
                page_contents = page['Contents']

                #iterating through the directories in the config
                for directory in bucket['Directories']:
                    lookup_directory = filter(None, directory['Directory'].split('/'))
                    
                    #This checks if the comparison type is xml
                    if directory['compare_type'] == 'check_xml':
                        for item in page_contents:
                            lookup_item = filter(None, item[u'Key'].split('/'))

                            #The lookup_item is the file from the s3 call contents and the lookup_directory is the 
                            # directory under which we are looking 
                            if lookup_directory and lookup_item:
                                if lookup_directory[0] in lookup_item[0] and len(lookup_item) == len(lookup_directory) + 1:

                                    if ".xml" in lookup_item[1]:
                                        for the_file in directory['file_list']:
                                            if item[u'Key'].split("/")[-1] in the_file['filename']:
                                                #if the file is in the directory and xml than read it
                                                s3_data_for_key = read_s3_data(bucket['bucketname'],item[u'Key'], the_array['RoleArn'])
                                                temp_dir.append({item[u'Key'].split("/")[-1]:s3_data_for_key,"filekey":the_file["filekey"]})
                                                break
                                                
                            #if the files being looked for are in the root directory of the bucket than these operations will
                            # be used to retrieve xml data
                            elif len(lookup_directory) == 0 and lookup_item:
                                if len(lookup_item) == 1:
                                    # add values to be associated with each directory
                                    if ".xml" in lookup_item[0]:
                                        for the_file in directory['file_list']:
                                            if item[u'Key'].split("/")[-1] in the_file['filename']:
                                                s3_data_for_key = read_s3_data(bucket['bucketname'], item[u'Key'],the_array['RoleArn'])
                                                temp_dir.append({item[u'Key'].split("/")[-1]: s3_data_for_key,"filekey": the_file["filekey"]})
                                                break

                    if temp_dir:
                        #The array of file data is input into the dictionary of directories
                        store_result[directory['Directory']] = temp_dir
                        temp_dir = []

            if store_result:
                store_bucket_result.append({bucket['bucketname']: store_result})
                store_result = dict()

        except Exception, e:
            print "Error in doing call for bucket " + str(e)
    return store_bucket_result

#compare the file versions
def compare_file_version(master_arr_comp, team_arr_comp):
    if master_arr_comp["version"] == team_arr_comp["version"]:
        return 1
    else:
        return 2


def get_team_name(m_data):
    for data in m_data['Directory_List']:
        for directory in data:
            return data['team_name']


#Compare the data retrieved from the s3 calls for master and secondary data sets 
def s3_compare_master_team(m_array, tkey, team_name):

    s3_data = []

    for m_item in m_array:
        for m_stuff in m_array[m_item]:
                for t_item in tkey:
                    for t_stuff in tkey[t_item]:

                        #compare directories
                        if m_stuff == t_stuff:

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

                                                            #compare the file key and os names
                                                            if the_m["os"] == the_t["os"] and m_file['filekey'] == t_file['filekey']:
                                                                amatch = compare_file_version(the_m,the_t)

                                                                #Formats the file name and version for master and secondary that slack will output
                                                                current_t_file_name = "\n\n"+str(t_system).split(".")[0] +"\n"+ str(the_t['version'])
                                                                current_m_file_name = "\n\n" + str(m_system).split(".")[0] + "\n" + str(the_m['version'])

                                                                if amatch == 2:
                                                                    amatch_status = False
                                                                    
                                                                if len(master_ver) > 0 and len(team_ver) > 0:
                                                                    if current_m_file_name not in master_ver and current_m_file_name not in team_ver:
                                                                        master_ver.append(current_m_file_name)
                                                                        team_ver.append(current_t_file_name)
                                                                else:
                                                                    master_ver.append(current_m_file_name)
                                                                    team_ver.append(current_t_file_name)

                                                                #if there is one mismatch between master and secondary data in directory
                                                                # files than amatch_status remains false until next directory
                                                                if amatch_status == False:
                                                                    amatch = 2
                                                                else:
                                                                    amatch = 1

                            if m_stuff == '':
                                m_stuff = str(m_item)

                            if t_stuff == '':
                                t_stuff = str(t_item)
                            #This is the dictionary that the compare_output module can decipher for output
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

    if master_plugin_data:
        team_plugin_data = get_s3_data(team_array)

        
        for m_plugin_data in master_plugin_data:
            for t_plugin_data in team_plugin_data:
                s3_compare_result = s3_compare_master_team(m_plugin_data, t_plugin_data, team_name)
                if s3_compare_result:
                    if compared_data:
                        compared_data = compared_data + s3_compare_result
                    else:
                        compared_data = s3_compare_result

    return {'s3 Artifact': compared_data}


