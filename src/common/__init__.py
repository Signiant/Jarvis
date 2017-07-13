import requests
import os
import boto3
import requests
import logging
import json

def create_graph(graphTitle, xAxisName, xAxisData, yAxisName, yAxisData, timestamps):
	with open(os.path.join(os.path.dirname(__file__), 'CHATURL_API_KEY')) as f:
		chaturl_api_key = f.read().strip()

	url = "https://charturl.com/short-urls.json?api_key=" + chaturl_api_key

	headers = {
		'Content-Type': 'application/json'
	}

	body = {
    	'template': 'simple-timeseries',
    	'options': {
       		'data': {
           		'columns': [
           			["x"] + timestamps,
               		[xAxisName] + xAxisData,
               		[yAxisName] + yAxisData
           		]
       		}
    	}
	}


	ret = requests.post(url, json=body, headers=headers, verify=False, allow_redirects=True)
	
	returl = ret.text.split("\"")[3]
	attachment = {"text": graphTitle, "image_url": returl, "fallback": "Something went wrong...", "color": "#9933ff"}

	return attachment


# retrieve json data from super jenkins for build urls
def get_superjenkins_data(beginning_script_tag, ending_script_tag, superjenkins_link=None,superjenkins_key=None):

	cached_items = None
	cached_array = None

	# if call to s3 bucket to recieve superjenkins data fails than call local superjenkins_link
	if superjenkins_key:
		try:
			s3 = boto3.resource('s3')
			logging.info("Retrieving file from s3 bucket for superjenkins data")

			my_bucket = superjenkins_key[:superjenkins_key.find("/")]
			my_key = superjenkins_key[superjenkins_key.find("/")+1:]

			obj = s3.Object(my_bucket, my_key)
			json_body = obj.get()['Body'].read()

			start = json_body.index(beginning_script_tag) + len(beginning_script_tag)
			end = json_body.index(ending_script_tag, start)
			cached_items = json.loads(json_body[start:end])

			for items in cached_items:
				cached_array = cached_items[items]

			logging.info("Superjenkins data retrieved and json loaded")

		except Exception, e:
			print "Error in retrieving and creating json from s3 superjenkins_key ==> " + str(e)


	if cached_array == None and superjenkins_link:
		try:
			returned_data = requests.get(superjenkins_link)
			returned_data_iterator = returned_data.iter_lines()

			for items in returned_data_iterator:
				if beginning_script_tag in items:
					cached_items = items.replace(beginning_script_tag, "").replace(ending_script_tag,"")
					break

			for items in json.loads(cached_items):
				cached_array = json.loads(cached_items)[items]

		except Exception, e:
			print "Error in retrieving and creating json from superjenkins ==> " + str(e)

	return cached_array
