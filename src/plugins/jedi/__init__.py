import random
import os
def main(*args):
  f = open("plugins/jedi/jediquotes", "r")
  data = f.readlines()

  return random.choice(data)

def about():
  return "This plugin returns a random Star Wars quote"

def information():
	return """This plugin picks a random star wars related quote and displays it."""