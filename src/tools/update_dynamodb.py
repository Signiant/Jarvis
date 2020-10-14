import boto3
import json
from datetime import datetime
from pytz import timezone

EST = timezone('US/Eastern')
CURRENT_DATETIME=datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S')

def update_dynamoDB(global_table_name, query_id, slack_data):
    """
    update jarvis data to dynamoDB, seperate by queryId,
    :param query_id: query attached together by + sign
    :param slack_data: a list
    :return:
    """
    # convert list to string for dynamodb storage
    slack_data = json.dumps(slack_data)
    session = boto3.session.Session(region_name='us-east-1')
    iam_client = session.client('dynamodb')
    list_group_detail = iam_client.update_item(TableName=global_table_name,
                                               Key={'queryId': {'S': query_id}},
                                               ExpressionAttributeNames={'#S': 'slackData','#D': 'dateTimeData'},
                                               ExpressionAttributeValues={':s': {'S': slack_data},':d': {'S': CURRENT_DATETIME}},
                                               ReturnValues='ALL_NEW',
                                               UpdateExpression='SET #S = :s, #D = :d')

    # print(list_group_detail['ResponseMetadata'])
    if list_group_detail['ResponseMetadata']['HTTPStatusCode'] == 200:
        print("update slackData to Database {0} successfully".format(global_table_name))


def extract_dynamoDB(global_table_name, query_id):
    session = boto3.session.Session(region_name='us-east-1')
    iam_client = session.client('dynamodb')
    get_data = iam_client.get_item(TableName=global_table_name,
                                            Key={'queryId': {'S': query_id}},
                                            ProjectionExpression='slackData,dateTimeData')
    # print(get_data)
    if 'Item' in get_data:
        db_data = get_data['Item']['slackData']['S']
        date_time_data = get_data['Item']['dateTimeData']['S']
        parsed_data = json.loads(db_data)
        # print(date_time_data)
        # print(len(parsed_data))
        # print(parsed_data)
        return parsed_data, date_time_data
    else:
        print("Jarvis Query not found in DynamoDB")
        return False

if __name__ == '__main__':
    print("hello world: use this for debug")