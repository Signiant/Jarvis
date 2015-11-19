import random
import os
def main(*args):
  print os.getcwd()
  f = open("plugins/jedi/jediquotes", "r")
  data = f.readlines()

  return random.choice(data)

def about():
  return "This plugin returns a random Star Wars quote"

def information():
	return """I see that the force is weak in this one...
	Just use Jarvis jedi. That's it!"""

