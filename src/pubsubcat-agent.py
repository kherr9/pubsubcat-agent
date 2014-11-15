#!/usr/bin/python
from azure.servicebus import ServiceBusService, Message, Topic, Subscription, Queue
from azure import WindowsAzureMissingResourceError
from azure.storage import BlobService
import json
import pygame
import urllib
import threading
import os, sys, traceback, subprocess
import time, datetime
import socket
from urlparse import urlparse
import fcntl
import struct
import logging

print 'Starting mLevel PubSubCat - FOR REAL'


# get configurations
config = json.load(open('config.json'))

service_namespace = config["service_namespace"]
shared_access_key_name = config["shared_access_key_name"]
shared_access_key_value = config["shared_access_key_value"]
topic_path = config["topic_path"]
subscription_name_prefix = config["subscription_name_prefix"]
storage_account_name = config["storage_account_name"]
storage_account_key = config["storage_account_key"]

hostname = socket.gethostname()
if "hostname" in config:
	hostname = config["hostname"]

logger = create_logger(hostname)
logger.debug("Created logger!!!")
	
subscription_name = subscription_name_prefix + hostname.lower() # add machine name
	
# configure logger
	
print "Connecting as " + hostname
print "Connecting to " + service_namespace
print "with key " + shared_access_key_name

	
def create_service_bus_service():
	return ServiceBusService(service_namespace,
					shared_access_key_name=shared_access_key_name,
					shared_access_key_value=shared_access_key_value)
					
def init_service_bus():
	sbs = create_service_bus_service()
	
	# create subscription for THIS machine queue
	subscription = Subscription()
	subscription.default_message_time_to_live = 'PT1M'	#1m

	# create subscriptions to agent topic
	print "Creating subscription " + subscription_name + " for topic " + topic_path + "..."
	sbs.create_subscription(topic_path, subscription_name, subscription)
	
	print "create publishing topics"
	sbs.create_topic("t.mlevel.pubsubcat.messages.agent.agentevent")
	sbs.create_topic("t.mlevel.pubsubcat.messages.agent.agentlog")

def create_logger(name):
	logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',level=logging.DEBUG)
	logger = logging.getLogger(name)
	return logger;

def publish_log(message):
	sbs = create_service_bus_service()
	body = {
		"hostname": hostname,
		"level": "debug",
		"message": message
	}
	js = json.dumps(body)
	msg = Message(js.encode('utf-8'), custom_properties={"messagetype":"MLevel.PubSubCat.Messages.Agent.AgentLog"})
	sbs.send_topic_message("t.mlevel.pubsubcat.messages.agent.agentlog", msg)
	
def handle_play_audio(dict):
	print 'handling play audio'
	url = dict['url'];
	print 'Play audio: "' + url + '"'
	path = download_file(url)
	play_audio(path)
	
def handle_speak_text(dict):
	print 'handling speak text'
	msg = dict['text'];
	speak_text(msg);

def handle_take_photo(dict):
	print 'handling take photo'
	speak_text("HR Warning!!! I am taking a picture of you ...1 2 3...Go")
	ts = time.time()
	st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d-%H-%M-%S')
	filename = "CatPIC-" + st + ".jpg"
	os.system("/usr/bin/fswebcam -r 1600x900 --no-banner temp/" + filename)
	upload_to_blob(filename)
	os.remove("temp/" + filename)
	speak_text("Meow, Nice Pic...")
	
def handle_restart_agent(dict):
	print 'handling restart agent'
	# just raise exception to get out of control loop
	raise StopAgentException(dict['reason'])
	
class StopAgentException(Exception):
    pass
	
def download_file(url):
	# create local file path 
	o = urlparse(url)
	path = "temp/a" + o.path.replace("/", "_")
	# check if file exists
	if os.path.isfile(path):
		print "File already exists"
	else:
		# download file
		print "Downloading file to: " + path
		testfile = urllib.URLopener()
		testfile.retrieve(url, path)
	
	return path

def upload_to_blob(filename):
	#uploads to azure blob storage
	blob_service = BlobService(account_name=storage_account_name, account_key=storage_account_key)
	blob_service.create_container('pubsubcat-pics')
	blob_service.put_block_blob_from_path("pubsubcat-pics", hostname + "/" + filename, 'temp/' + filename)

def speak_text(msg):
	print 'Speak "' + msg + '"'
	# escape the string by removing double quotes
	msg = msg.replace("\"", "")
	os.system("/bin/bash Speech.sh \"" + msg + "\"")
	#os.system("/usr/bin/espeak -a 200 -s 150 -w temp/speakfile.wav \"" + msg + "\"")
	#play_audio("temp/speakfile.wav")
	
def play_audio(path):
	print "playing audio file " + path
	pygame.mixer.init()
	try:
		pygame.mixer.music.load(path)
		pygame.mixer.music.play()
		while pygame.mixer.music.get_busy() == True:
			continue
		"finished playing audio file"
	except:
		print "error playing audio file"
	pygame.mixer.quit()

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])

print get_ip_address("eth0")	
publish_log("My ip addres is: " + get_ip_address("eth0"))

def init():
	# Called once to init program
	print "Calling init"
	
	print "Ensuring temp directory"
	if not os.path.exists("temp"):
		print "Creating temp directory"
		os.makedirs("temp")
		
	init_service_bus()
		
	print "Completed init"

init()		
		
callbacks = {
	'MLevel.PubSubCat.Messages.Agent.PlayAudio': handle_play_audio,
	'MLevel.PubSubCat.Messages.Agent.SpeakText': handle_speak_text,
	'MLevel.PubSubCat.Messages.Agent.TakePhoto': handle_take_photo,
	'MLevel.PubSubCat.Messages.Agent.RestartAgent': handle_restart_agent
}

def process_messages():
	# now start listening to subscription
	print 'Now listening to incoming messages...'
	signaled_to_quit = False
	sbs = None
	while not signaled_to_quit:
		try:
			if sbs is None:
				print "Service bus service has does not exist, creating..."
				sbs = create_service_bus_service()
		
			print 'Waiting for next message...'
			msg = sbs.receive_subscription_message(topic_path, subscription_name, peek_lock=False)
			if msg.body is not None:
				print (msg.body)
				message_type = msg.custom_properties['messagetype']
				publish_log("Got message type: " + message_type + ", Body: " + msg.body)
				print 'got message type: ' + message_type
				dict = json.loads(msg.body)
				print (dict)
				if message_type in callbacks:
					callbacks[message_type](dict)
					publish_log("Completed task: " + message_type)
				else:
					print 'Unknown message type: ' + message_type
					publish_log("Unknown task: " + message_type)
			else:
				print 'No message was delivered'
		except WindowsAzureMissingResourceError:
			print 'The subscription we are listening to no longer exists'
			publish_log('The subscription we are listening to no longer exists')
			sbs = None
		except KeyboardInterrupt:
			print 'Called to quit'
			publish_log("Called to quit")
			signaled_to_quit = True
		except StopAgentException as e:
			print 'Caught exception StopAgentException'
			print e
			publish_log(str(e))
			signaled_to_quit = True
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			print "*** print_exception:"
			traceback.print_exception(exc_type, exc_value, exc_traceback,
									  limit=2, file=sys.stdout)
			publish_log("An unhandle error!!!")

process_messages()
