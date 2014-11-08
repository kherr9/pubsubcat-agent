#!/usr/bin/python
import time
import os

print "Starting PubSubCat supervisor"

def update_src():
	print "checking for latest code..."
	os.system("git fetch -v")
	print "completed checking for latest code"

def run_agent():
	print "starting agent..."
	os.system("python pubsubcat-agent.py")
	print "agent stopped."

def main():
	signaled_to_quit = False
	while not signaled_to_quit:
		try:
			update_src()
			run_agent()
		except KeyboardInterrupt:
			print "Keyboard Interrupt to quit"
			signaled_to_quit = True
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			print "*** print_exception:"
			traceback.print_exception(exc_type, exc_value, exc_traceback,
									  limit=2, file=sys.stdout)
			print "Sleeping for 10 seconds..."
			time.sleep(10)		  
			print "Done sleeping"
		
main()
	
print "Stopping PubSubCat supervisor"
