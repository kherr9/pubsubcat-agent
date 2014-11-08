import os

print "Starting PubSubCat supervisor"

def update_src():
	print "checking for latest code..."
	os.system("git pull")
	print "completed checking for latest code"

def run_agent():
	print "starting agent..."
	os.system("python pubsubcat-agent.py")
	print "agent stopped."

signaledStop = False
while not signaledStop:

	update_src()

	run_agent()

print "Stopping PubSubCat supervisor"
