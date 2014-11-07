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

print 'Starting mLevel PubSubCat'


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
						
subscription_name = subscription_name_prefix + hostname.lower() # add machine name
	
print "Connecting as " + hostname
print "Connecting to " + service_namespace
print "with key " + shared_access_key_name

def create_service_bus_service():
	x = ServiceBusService(service_namespace,
						shared_access_key_name=shared_access_key_name,
						shared_access_key_value=shared_access_key_value)
						

	# create subscription for THIS machine queue
	subscription = Subscription()
	subscription.default_message_time_to_live = 'PT1M'	#1m

	# create subscriptions to agent topic
	print "Creating subscription " + subscription_name + " for topic " + topic_path + "..."
	x.create_subscription(topic_path, subscription_name, subscription)
	
	return x

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

def handle_play_audio(dict):
	print 'handling play audio'
	url = dict['url'];
	print 'Play audio: "' + url + '"'
	path = download_file(url)
	play_audio(path)
	##print 'TODO: Unable to play sounds right now'
	##os.system("/usr/bin/omxplayer -o local --no-osd " + path + " >> /dev/null")
	##subprocess.call(["/usr/bin/omxplayer", "-o", "local", path])
	
def handle_speak_text(dict):
	print 'handling speak text'
	msg = dict['text'];
	print 'Speak "' + msg + '"'
	msg = msg.replace("\"", "")
	os.system("/usr/bin/espeak -a 200 -s 150 -w temp/speakfile.wav \"" + msg + "\"")
	play_audio("temp/speakfile.wav")
	#engine = pyttsx.init()
	# slow down the speech rate (speed)
	#rate = engine.getProperty('rate')
	#engine.setProperty('rate', rate-50)
	#engine.setProperty('volume', 1.0)
	#engine.say(msg)
	#engine.runAndWait()

def download_file(url):
	# ensure temp directory
	tempFolder = "temp"
	if not os.path.exists(tempFolder):
		os.makedirs(tempFolder)
	# create local file path 
	o = urlparse(url)
	path = tempFolder + "/a" + o.path.replace("/", "_")
	# check if file exists
	if os.path.isfile(path):
		print "File already exists"
	else:
		# download file
		print "Downloading file to: " + path
		testfile = urllib.URLopener()
		testfile.retrieve(url, path)
	
	return path

def handle_take_photo(dict):
        speak_dict = {'text':'HR Warning!!! I am taking a picture of you ...1 2 3...Go'}
        handle_speak_text(speak_dict)
	# ensure temp directory
	tempFolder = "temp"
	if not os.path.exists(tempFolder):
		os.makedirs(tempFolder)
        ts = time.time()
	st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d-%H-%M-%S')
        filename = "CatPIC-" + st + ".jpg"
	os.system("/usr/bin/fswebcam -r 1600x900 --no-banner temp/" + filename)
	uploadToBlob(filename)
	os.remove("temp/" + filename)
        speak_dict = {'text':'Meow, Nice Pic...'}
        handle_speak_text(speak_dict)


def uploadToBlob(filename):
	#uploads to azure blob storage
	blob_service = BlobService(account_name=storage_account_name, account_key=storage_account_key)
	blob_service.create_container('pubsubcat-pics')
	blob_service.put_block_blob_from_path("pubsubcat-pics", hostname + "/" + filename, 'temp/' + filename)


callbacks = {
	'MLevel.PubSubCat.Messages.Agent.PlayAudio': handle_play_audio,
	'MLevel.PubSubCat.Messages.Agent.SpeakText': handle_speak_text,
	'MLevel.PubSubCat.Messages.Agent.TakePhoto': handle_take_photo,
}

def process_messages():
	# now start listening to subscription
	print 'Now listening to incoming messages...'
	signaledToQuit = False;
	sbs = None
	while not signaledToQuit:
		try:
			if sbs is None:
				print "Service bus service has does not exist, creating..."
				sbs = create_service_bus_service()
		
			print 'Waiting for next message...'
			msg = sbs.receive_subscription_message(topic_path, subscription_name, peek_lock=False)
			if msg.body is not None:
				print (msg.body)
				message_type = msg.custom_properties['messagetype']
				print 'got message type: ' + message_type
				dict = json.loads(msg.body)
				print (dict)
				if message_type in callbacks:
					callbacks[message_type](dict)
				else:
					print 'Unknown message type: ' + message_type
			else:
				print 'No message was delivered'
		except WindowsAzureMissingResourceError:
			print 'The subscription we are listening to no longer exists'
			sbs = None
		except KeyboardInterrupt:
			print 'Called to quit'
			signaledToQuit = True
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			print "*** print_exception:"
			traceback.print_exception(exc_type, exc_value, exc_traceback,
									  limit=2, file=sys.stdout)

process_messages()
	
#t = threading.Thread(target=process_messages)
#t.daemon = True
#threading.Threadt.start()

#char = raw_input("Press <Enter> to exit program\n")	

#print 'Ending program'
