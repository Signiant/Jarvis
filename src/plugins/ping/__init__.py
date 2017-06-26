#append path of the current subdirectory module to sys.path so any modules in the current directory will load
dir_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(dir_path)

def main(*args):
  return "pong"

def about():
	return "This plugin returns a pong message"

def information():
	return """Up for a game?"""
