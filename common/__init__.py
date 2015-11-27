import requests
import os

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