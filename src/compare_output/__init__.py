import logging
import pprint

def id():
    return "output"

def log(message):
    print id() + ": " + message

def get_themessage(value):
    if value == 1:
        return "Matches Master"
    elif value == 2:
        return "Does not match Master"
    elif value == 3:
        return "Branch repo"


def display_results(data_array):
    for value in data_array:
        themessage = get_themessage(value["Match"])
        print("M_Environment = [" + value['master_env'] + "] *  M_Version = " + value['master_version'] +"master updated on "
              + value["master_updateddate"].strftime('%m/%d/%Y %H:%M:%S')
              + " * Team: " +value['team']+ " T_Environment = ["+value['team_env'] + "] * T_Version " + value['team_version']
              + "master updated on "+ value["team_updateddate"].strftime('%m/%d/%Y %H:%M:%S')
              +" === "+ themessage+"\n")


def add_indent_fields(fields):
    fields.append({
            "title": "",
            "value": "",
            "short": "true"
        })
    fields.append({
        'title': "",
        'value': "",
        'short': "true"
    })
    return 1


#format time if data available
def format_the_time(thetime):
    if thetime == "":
        time_updated =""
    else:
        time_updated = "\nUpdated On: "+thetime.strftime('%m/%d/%Y %H:%M:%S')
    return time_updated


#compress string is larger than 28 chars
def shorten_input(thestring):
    if len(thestring) > 28:
        thestring = thestring[:25]+"..."
        return thestring
    else:
        return thestring


def append_to_field(fields, value, mastername):

    fields.append({
        # adding team data
            "title": shorten_input(value['team_env']),
            "value": value['team_version'] + format_the_time(value["team_updateddate"]),
            "short": "true"
    })
    fields.append({
        # adding master data
        #--trying mastername+": "+
        'title': shorten_input(value['master_env']),
        'value': value['master_version'] + format_the_time(value["master_updateddate"]),
        'short': "true"
    })
    #adding more slack fields to create vertical spacing
    add_indent_fields(fields)
    add_indent_fields(fields)

    return 1

#create the title containing left and right that will be the title
def create_title_dictionary_add_in(field, left_title,right_title,color):

	insert_the_left_title = {
		'title': left_title,
		'value': "",
		'short': "true"
	}

	insert_the_right_title = {
		'title': right_title,
		'value': "",
		'short': "true"
	}

	field.insert(0, insert_the_left_title)
	field.insert(1, insert_the_right_title)

	return {'fields': field, 'color': color}


# create attachment for each plugin
def create_plugin_format(thedata, thetitle_beginning):
	field_matching = []
	field_not_matching = []
	field_repo = []

	theattachment = []

	for value in thedata:
		if value["Match"] == 1:
			append_to_field(field_matching, value, value['mastername'])
		if value["Match"] == 2:
			append_to_field(field_not_matching, value, value['mastername'])
		if value["Match"] == 3:
			append_to_field(field_repo, value, value['mastername'])

	# master team name with first letter capitalized
	master_name_edited = str(value['mastername']).title()

	# append not matching
	if field_not_matching:
		left_the_title = thetitle_beginning.title() + "s not matching " + master_name_edited
		right_the_title = shorten_input(master_name_edited + " " + thetitle_beginning + "s ")
		the_color = "#ec1010"
		theattachment.append(create_title_dictionary_add_in(field_not_matching, left_the_title,right_the_title,the_color))

	# append repos
	if field_repo:
		left_the_title = thetitle_beginning.title() + " dev branches"
		right_the_title = shorten_input(master_name_edited + " " + thetitle_beginning + "s ")
		the_color = "#fef65b"
		theattachment.append(create_title_dictionary_add_in(field_repo, left_the_title, right_the_title, the_color))

	# append matching
	if field_matching:
		left_the_title = thetitle_beginning + "s matching " + master_name_edited
		right_the_title = shorten_input(master_name_edited + " " + thetitle_beginning + "s ")
		the_color = "#7bcd8a"
		theattachment.append(create_title_dictionary_add_in(field_matching, left_the_title, right_the_title, the_color))


	return theattachment


#plugin data array is empty
def no_elements_found(thetitle_beginning,message=None):
    theattachment = []
    thetitle = thetitle_beginning+message
    the_color = "#9B30FF"
    theattachment.append({'title': thetitle.title(), 'color': the_color})
    return theattachment


#main output to slack function
def slack_payload(data_array, eachteam):
    attachments = []
    logging.debug("printing data array in output_slack_payload")
    logging.debug(data_array)
    if data_array:
        for theplugin in data_array:
            if data_array[theplugin]:
                attachments = attachments + create_plugin_format(data_array[theplugin], theplugin)
            else:
                attachments = attachments + no_elements_found(theplugin, " not found")
    else:
        attachments = attachments + no_elements_found("Unable to Retrieve Data")

    print("printing attachments")
    print(attachments)

    return  attachments

