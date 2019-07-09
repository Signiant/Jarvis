import json
import boto3
import re
import os
import sys
import compare_output
from . import s3_compares


# to by pass initial setting of default values
def extract_from_text(text):
    if 'compare' in text and text.count('in') > 1:
        return False
    else:
        return True


def main(text):
    regionList = ['us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-2']
    region = regionList[0]

    awsKeyId = None
    awsSecretKey = None
    awsSessionToken = None
    loadedbuckets = dict()
    tokens = []
    the_account = None
    the_role = None
    region = None

    text.pop(0)  # remove command name
    if len(text) == 0:
        return "You did not supply a query to run"
    if text[0] == 'help':
        return information()

    # This function checks text if it contains one of the commands that should not extract region and account from,
    # for example if user enters the compare command then this process is bypassed
    if extract_from_text(text):
        if 'in' in text:
            while text[-1] != 'in':
                tokens.append(text.pop())
            extractedRegion = re.search(r'[a-z]{2}-[a-z]+-[1-9]{1}', " ".join(tokens))
            if extractedRegion:
                region = extractedRegion.group()
                tokens.remove(region)
            text.remove('in')

        # default loading of bucket values
        config = None
        if os.path.isfile("./aws.config"):
            with open("aws.config") as f:
                config = json.load(f)
                if config.get('s3'):
                    for account in config['s3']['Accounts']:
                        if account["RoleArn"] == "" and account["AccountName"] == "":
                            loadedbuckets = account["Buckets"]

        # this will look at the command to see if it contains an account that is different and set the
        # the_account, the_role, loadedbuckets
        if len(tokens) > 0 and config != None:
            for account in config['s3']['Accounts']:
                if account['AccountName'] in tokens:
                    the_account = account['AccountName']
                    the_role = account["RoleArn"]
                    loadedbuckets = account['Buckets']
                    tokens.remove(account['AccountName'])
            if len(tokens) > 0:
                return "Could not resolve " + " ".join(tokens)
        elif len(tokens) > 0:
            return "Could not locate aws.config file"

        if the_role:
            sts_client = boto3.client('sts')
            assumedRole = sts_client.assume_role(RoleArn=the_role, RoleSessionName="AssumedRole")
            awsKeyId = assumedRole['Credentials']['AccessKeyId']
            awsSecretKey = assumedRole['Credentials']['SecretAccessKey']
            awsSessionToken = assumedRole['Credentials']['SessionToken']

        session = boto3.session.Session(aws_access_key_id=awsKeyId,
                                        aws_secret_access_key=awsSecretKey,
                                        aws_session_token=awsSessionToken)
        s3 = session.client("s3")

    if 'list' in text:
        text.remove("list")
        ret = ""
        if 'buckets' in text:
            try:
                s3_buckets = s3.list_buckets()['Buckets']

            except Exception as e:
                print(e)
                return "Could not list buckets in " + region

            if len(s3_buckets) == 0:
                return "There are no s3 buckets associated with this region: " + region

            # create list of buckets to output to slack
            for bucket in s3_buckets:
                for b in loadedbuckets[region]:
                    if bucket['Name'] == b['bucketname']:
                        ret = ret + str(bucket['Name']) + "\n"
            return ret

        if 'files' in text:
            text.remove('files')
            print(text)

            if "filter" in text:
                if len(text) == 3:
                    lookup = text[text.index("filter")+1]
                    text.remove(text[text.index("filter")+1])
                    text.remove('filter')
                else:
                    return "Filter is missing lookup directories"

                one_bucket_search = False

                for b in loadedbuckets[region]:
                    try:
                        paginator = s3.get_paginator('list_objects_v2')
                        if len(text) == 1:
                            page_iterator = paginator.paginate(Bucket=text[0])
                            ret = ret + "\n\nBucket: " + str(text[0])
                            one_bucket_search = True
                        else:
                            page_iterator = paginator.paginate(Bucket=b['bucketname'])
                            ret = ret + "\n\nBucket: " + str(b['bucketname'])

                        for page in page_iterator:
                            for item in page['Contents']:
                                page_item = [_f for _f in item['Key'].split('/') if _f]
                                lookup_array = [_f for _f in lookup.split('/') if _f]

                                if len(page_item) == len(lookup_array)+1:
                                    l_iterator = 0
                                    check_match = 0
                                    while l_iterator < len(lookup_array):
                                        if page_item[l_iterator] == lookup_array[l_iterator]:
                                            check_match = check_match + 1
                                        l_iterator = l_iterator + 1
                                    if check_match == len(lookup_array):
                                        ret = ret + "\n\nobject: " + item['Key'] +"\nLast Modified: "+item['LastModified'].strftime('%m/%d/%Y %H:%M:%S')
                        # if user requested one bucket specifically than return data for the one bucket
                        if one_bucket_search:
                            return ret

                    except Exception as e:
                        print(e)
                        return "Could not list buckets in " + region
            else:
                # all top directories will be returned in the buckets or bucket if specified
                s3_dictionary = []

                one_bucket_search = False

                for b in loadedbuckets[region]:
                    try:
                        paginator = s3.get_paginator('list_objects_v2')
                        if len(text) == 1:
                            page_iterator = paginator.paginate(Bucket=text[0])
                            ret = ret + "\n\nBucket: " + str(text[0])
                            one_bucket_search = True
                        else:
                            page_iterator = paginator.paginate(Bucket=b['bucketname'])
                            ret = ret + "\n\nBucket: " + str(b['bucketname'])


                        for page in page_iterator:
                            for item in page['Contents']:
                                page_item = item['Key'].split('/')[0]
                                if page_item not in s3_dictionary:
                                    ret = ret +"\n"+page_item
                                    s3_dictionary.append(page_item)

                        if one_bucket_search:
                            return ret

                    except Exception as e:
                        print(e)
                        return "Could not list buckets in " + region

            return ret

    elif 'compare' in text:

        print(text)
        text.remove("compare")

        if "with" in text and (len([_f for _f in text if _f]) == 9 or len([_f for _f in text if _f]) == 7):

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
                    master_data = get_in_s3_compare_data(config, master_args, master_args_eval)
                    team_data = get_in_s3_compare_data(config, team_args, team_args_eval)

                else:
                    return "Config file was not loaded"

                if master_data and team_data:
                    compared_data = s3_compares.main_eb_check_versions(master_data, team_data)
                    return compare_output.slack_payload(compared_data, get_team_name(team_data))

                else:
                    return "Values could not be retrieved from operation, 'Jarvis eb help'"
            else:
                return "Invalid region or account information entered"
        else:
            return "Invalid arguments entered to complete comparison"
    else:
        return "I did not understand the query. Please try again."


def about():
    return "This plugin returns requested information regarding AWS s3 Buckets"


def information():
    return """This plugin returns various information about clusters and services hosted on s3.
    The format of queries is as follows:
    jarvis s3 list buckets <in region/account> [sendto <user or channel>]
    jarvis s3 list files [<bucket>] <in region/account> [sendto <user or channel>]
    jarvis s3 compare [<bucket>] within <region> <account> with [<bucket>] within <account>  [sendto <user or channel>]"""


def eval_args(args, regionList):
    args = [_f for _f in args if _f]
    # this indicates user did not specify a bucket
    if len(args) == 3:
        if args.index("within") == 0 and args[1] in regionList:
            return 1
        else:
            return 0
    # this indicates user specified a bucket
    elif len(args) == 4:
        if args.index("within") == 1 and args[2] in regionList:
            return 2
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


# if the user specifies a bucket this will attach directories from that bucket to the data to be compared
def get_data_for_specific_bucket(dataset, bucket):
    arr = []
    for data in dataset:
        if data['bucketname'] == bucket:
            arr.append(data)
        return arr


# if the role arn is blank, use team names to search for account
def check_team_name(account, result, bucket=None):
    check_result = False
    for dir in account['Buckets'][result['region']]:
        if 'team_name' in dir:
            if result['AccountName'] == dir['team_name']:
                result['RoleArn'] = account['RoleArn']
                # set the directory
                if account['Buckets']:
                    for region in account['Buckets']:
                        if region == result['region']:
                            if bucket:
                                result['Directory_List'] = get_data_for_specific_bucket(account['Buckets'][region], bucket)
                            else:
                                result['Directory_List'] = account['Buckets'][region]

                check_result = True
    return check_result


def get_in_s3_compare_data(config, args, args_eval):
    if args_eval == 1:
        # values from user arguments
        result = dict()
        result['region'] = args[1]
        result['AccountName'] = args[2]
    elif args_eval == 2:
        result = dict()
        result['region'] = args[2]
        result['AccountName'] = args[3]
        result['Bucket'] = args[0]

    if config.get('s3'):
        config = config['s3']['Accounts']
    else:
        return "Config file not loaded properly"

    for account in config:
        if 'RoleArn' in result:
            break
        elif result['AccountName'] == account['AccountName'] and result['region'] in account['Buckets']:
            result['RoleArn'] = account['RoleArn']
            # set the directory
            if account['Buckets']:
                for region in account['Buckets']:
                    if region == result['region']:
                        # the user specified a bucket than search just in that bucket
                        if 'Bucket' in result:
                            result['Directory_List'] = get_data_for_specific_bucket(account['Buckets'][region], result['Bucket'])
                        else:
                            result['Directory_List'] = account['Buckets'][region]
            break
        elif result['region'] in account['Buckets']:
            if 'Bucket' in result:
                if check_team_name(account, result, result['Bucket']):
                    if result['RoleArn']:
                        break
            else:
                if check_team_name(account, result):
                    if result['RoleArn']:
                        break

    if ('RoleArn' in result) == False or ('RoleArn' in result) == False or not ('Accountname' in result) == False or len(result['Directory_List']) < 1:
        result = dict()

    return result


def get_team_name(m_data):
    for data in m_data['Directory_List']:
        for directory in data:
            return data['team_name']
