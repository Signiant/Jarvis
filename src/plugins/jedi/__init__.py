import random
import os, sys

#append path of the current subdirectory module to sys.path so any modules in the current directory will load
dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path)



def main(*args):
  f = open("plugins/jedi/jediquotes", "r")
  data = f.readlines()

  return random.choice(data)

def about():
  return "This plugin returns a random Star Wars quote"

def information():
	return """This plugin picks a random star wars related quote and displays it."""
