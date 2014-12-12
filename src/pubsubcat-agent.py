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
import logging.handlers
import serial
import urllib2

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
	
def create_logger(name):
	logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',level=logging.DEBUG)
	l = logging.getLogger(name)
	http_handler = logging.handlers.HTTPHandler(
		'pubsubcat.mlevel.net',
		'/agent/log',
		method='POST',
	)
	http_handler.setFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	http_handler.setLevel(logging.DEBUG)
	l.addHandler(http_handler)
	return l;
	
logger = create_logger(hostname)
logger.debug("Created logger!!!")
	
subscription_name = subscription_name_prefix + hostname.lower() # add machine name
	
# configure logger
logger.info("Starting mLevel PubSubCat - FOR REAL")
logger.info("Connecting as " + hostname)
logger.info("Connecting to " + service_namespace)	
logger.info("with key " + shared_access_key_name)	

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
	logger.info("Creating subscription " + subscription_name + " for topic " + topic_path + "...")
	sbs.create_subscription(topic_path, subscription_name, subscription)
	
	logger.info("create publishing topics")
	sbs.create_topic("t.mlevel.pubsubcat.messages.agent.agentevent")
	sbs.create_topic("t.mlevel.pubsubcat.messages.agent.agentlog")
	
cached_temperature_reader = None
def get_temperature_reader():
	if cached_temperature_reader is None:
		logger.info('creating temp reader')
		cached_temperature_reader = serial.Serial('/dev/ttyACM0', 9600, timeout=5)
		# wait for arduino to initialize
		time.sleep(1)
	return cached_temperature_reader
	
def handle_play_audio(dict):
	logger.info('handling play audio')
	url = dict['url'];
	logger.info('Play audio: "' + url + '"')
	path = download_file(url)
	play_audio(path)
	
def handle_speak_text(dict):
	logger.info('handling speak text')
	msg = dict['text'];
	speak_text(msg);
	# temp solution to get reading here
	handle_read_temp_humidity(dict)
	
def handle_take_photo(dict):
	logger.info('handling take photo')
	speak_text("HR Warning!!! I am taking a picture of you ...1 2 3...Go")
	ts = time.time()
	st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d-%H-%M-%S')
	filename = "CatPIC-" + st + ".jpg"
	os.system("/usr/bin/fswebcam -r 1600x900 --no-banner temp/" + filename)
	upload_to_blob(filename)
	os.remove("temp/" + filename)
	speak_text("Meow, Nice Pic...")

def handle_read_temp_humidity(dict):
	logger.info('handling read temp humidity.')
	ser = get_temperature_reader()
	ser.write("hello world")
	ser.flush()
	response = ser.readline()
	logger.info(response)
	readings = response.split(',')
	if len(readings) >= 4:
		h = float(readings[0])
		c = float(readings[1])
		f = float(readings[2])
		hi = float(readings[3])
		body = {
			'Hostname': hostname,
			'Timestamp': str(unix_time(datetime.datetime.utcnow())),
			'Humidity':h,
			'TemperatureCelsius':c,
			'TemperatureFahrenheit':f,
			'HeatIndex':hi
		}
		
		bodyJson = json.dumps(body)
		logger.info(bodyJson)
		
		req = urllib2.Request('http://abc.com/api/posts/create')
		req.add_header('Content-Type', 'application/json')
		
		response = urllib2.urlopen(req, logger)
		logger.info(str(response))
		
	else:
		logger.info("Failed to reading temp/humidity sensor")
	logger.info('completed reading sensor')
	
def handle_restart_agent(dict):
	logger.info('handling restart agent')
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
		logger.info("File already exists")
	else:
		# download file
		logger.info("Downloading file to: " + path)
		testfile = urllib.URLopener()
		testfile.retrieve(url, path)
	
	return path

def upload_to_blob(filename):
	#uploads to azure blob storage
	blob_service = BlobService(account_name=storage_account_name, account_key=storage_account_key)
	blob_service.create_container('pubsubcat-pics')
	blob_service.put_block_blob_from_path("pubsubcat-pics", hostname + "/" + filename, 'temp/' + filename)

def speak_text(msg):
	logger.info('Speak "' + msg + '"')
	# escape the string by removing double quotes
	msg = msg.replace("\"", "")
	os.system("/bin/bash Speech.sh \"" + msg + "\"")
	#os.system("/usr/bin/espeak -a 200 -s 150 -w temp/speakfile.wav \"" + msg + "\"")
	#play_audio("temp/speakfile.wav")
	
def play_audio(path):
	logger.info("playing audio file " + path)
	pygame.mixer.init()
	try:
		pygame.mixer.music.load(path)
		pygame.mixer.music.play()
		while pygame.mixer.music.get_busy() == True:
			continue
		logger.info("finished playing audio file")
	except:
		logger.exception("Exception while playing file: " + path)
	pygame.mixer.quit()

def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15])
    )[20:24])

def unix_time(dt):
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = dt - epoch
    return delta.total_seconds()
	
def init():
	# Called once to init program
	logger.info("Calling init")
	
	logger.info("Ensuring temp directory")
	if not os.path.exists("temp"):
		logger.info("Creating temp directory")
		os.makedirs("temp")
		
	init_service_bus()
		
	logger.info("My ip addres is: " + get_ip_address("eth0"))
	
	logger.info("Completed init")

init()		
		

callbacks = {
	'MLevel.PubSubCat.Messages.Agent.PlayAudio': handle_play_audio,
	'MLevel.PubSubCat.Messages.Agent.SpeakText': handle_speak_text,
	'MLevel.PubSubCat.Messages.Agent.TakePhoto': handle_take_photo,
	'MLevel.PubSubCat.Messages.Agent.TakeTempAndHumidityReading': handle_read_temp_humidity,
	'MLevel.PubSubCat.Messages.Agent.RestartAgent': handle_restart_agent
}

def process_messages():
	# now start listening to subscription
	logger.info('Now listening to incoming messages...')
	signaled_to_quit = False
	sbs = None
	while not signaled_to_quit:
		try:
			if sbs is None:
				logger.info("Service bus service has does not exist, creating...")
				sbs = create_service_bus_service()
		
			logger.info('Waiting for next message...')
			msg = sbs.receive_subscription_message(topic_path, subscription_name, peek_lock=False)
			if msg.body is not None:
				print (msg.body)
				message_type = msg.custom_properties['messagetype']
				logger.info('got message type: ' + message_type + ", Body: " + msg.body)
				dict = json.loads(msg.body)
				logger.info(dict)
				if message_type in callbacks:
					callbacks[message_type](dict)
					logger.info("Completed task: " + message_type)
				else:
					logger.info( 'Unknown message type: ' + message_type)
			else:
				print 'No message was delivered'
		except WindowsAzureMissingResourceError:
			logger.exception("Got exception from azure service")
			sbs = None
		except KeyboardInterrupt:
			logger.info("Called to quit")
			signaled_to_quit = True
		except StopAgentException as e:
			logger.info("Caught exception StopAgentException")
			signaled_to_quit = True
		except:
			logger.exception("Got exception in process loop")

process_messages()

if cached_temperature_reader is not None:
	cached_temperature_reader.close()