import logging


def id():
    return "output"


def log(message):
    print((id() + ": " + message))


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
        print(("M_Environment = [" + value['master_env'] + "] *  M_Version = " + value['master_version'] +"master updated on "
              + value["master_updateddate"].strftime('%m/%d/%Y %H:%M:%S')
              + " * Team: " +value['team']+ " T_Environment = ["+value['team_env'] + "] * T_Version " + value['team_version']
              + "master updated on "+ value["team_updateddate"].strftime('%m/%d/%Y %H:%M:%S')
              +" === "+ themessage+"\n"))


# format time if data available
def format_the_time(thetime):
    if thetime == "":
        time_updated =""
    else:
        time_updated = "\nUpdated On: "+thetime.strftime('%m/%d/%Y %H:%M:%S')
    return time_updated


# compress string is larger than 28 chars
def shorten_input(thestring):
    if len(thestring) > 40:
        thestring = thestring[:40]+"..."
        return thestring
    else:
        return thestring


def append_to_field(fields, value):
    """
    insert data while sorting them into alphabetical order when display in slack
    :param fields: the list to be inserted.
    :param value: the values to be inserted into the fields list
    :return:
    """

    team_data = {
        # adding team data
            "title": shorten_input(value['team_env']),
            "value": value['team_version'] + format_the_time(value["team_updateddate"]),
            "short": "true"
    }
    master_data = {
        # adding master data
        # --trying mastername+": "+
        'title': shorten_input(value['master_env']),
        'value': value['master_version'] + format_the_time(value["master_updateddate"]),
        'short': "true"
    }
    blank_space = {
        'title': "",
        'value': "",
        'short': "true"
    }

    if len(fields) == 0 or fields[0]['title'] >= team_data['title']:
        fields.insert(0, team_data)
        fields.insert(1, master_data)
        fields.insert(2, blank_space)
        fields.insert(3, blank_space)

    elif len(fields) == 4:
        if team_data['title'] < fields[0]['title']:
            fields.insert(0, team_data)
            fields.insert(1, master_data)
            fields.insert(2, blank_space)
            fields.insert(3, blank_space)
        else:
            fields.insert(len(fields), team_data)
            fields.insert(len(fields), master_data)
            fields.insert(len(fields), blank_space)
            fields.insert(len(fields), blank_space)

    else:
        # since section in slack consist of left/right field then left/right blank space. compare every 4th field
        for i in range(0, len(fields) - 4, 4):

            if fields[i]['title'] <= team_data['title'] <= fields[i + 4]['title']:
                fields.insert(i + 4, team_data)
                fields.insert(i + 5, master_data)
                fields.insert(i + 6, blank_space)
                fields.insert(i + 7, blank_space)
                break

        else:
            fields.insert(len(fields), team_data)
            fields.insert(len(fields), master_data)
            fields.insert(len(fields), blank_space)
            fields.insert(len(fields), blank_space)

    return 1


# create the title containing left and right that will be the title
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
            append_to_field(field_matching, value)
        if value["Match"] == 2:
            append_to_field(field_not_matching, value)
        if value["Match"] == 3:
            append_to_field(field_repo, value)

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


# plugin data array is empty
def no_elements_found(thetitle_beginning,message=None):
    theattachment = []
    thetitle = thetitle_beginning+message
    the_color = "#9B30FF"
    theattachment.append({'title': thetitle.title(), 'color': the_color})
    return theattachment


# main output to slack function
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

    logging.debug("printing attachments")
    logging.debug(attachments)

    return  attachments

