import threading
import json
import requests
from time import time
#import ZeroSeg.led as led
from os import path


basepath = path.dirname(__file__)
filepath = path.abspath(path.join(basepath, "..", "buses.conf"))
with open(filepath) as conf: 
	# auth tokens for my dev account with TFL
	# NB TFL username is cp---3 registered with teach first email addr
	APP_ID = "8717f35a"
	APP_KEY = conf.readline()
	print(APP_KEY)

BUS_STOP_ID = "490006045W"  # Stratford Park
POINT = "/arrivals"
API_URI = "https://api.tfl.gov.uk/StopPoint/" + BUS_STOP_ID + POINT

DOWNLOAD_INTERVAL = 30  # download every 30 seconds
next_download = None

DISPLAY_INTERVAL = 5 # show each bus for this many seconds
next_display = None

class Bus:
	def __init__(self, id, line, time):
		self.id = id
		self.line = line
		self.time = time

buses = {}

def download():
	# get the bus stop arrivals data from the TFL API
	response = requests.get(API_URI)
	if response.status_code != 200:
		# TODO how to handle errors??
		return
	print(response.status_code)
	json_data = response.json()  # TFL API returns a list
	#print(json_data)
	
	# clear out the previous list of buses
	if len(json_data) == 0:
		return
	buses.clear()
	# process the json data to pull out just the interesting items
	for foo in json_data:
		print(type(foo))
		print(foo)
	for foo in json_data:
		bus_id = foo["vehicleId"]
		line = foo["lineName"]
		time = foo["timeToStation"]
		buses[time] = Bus(bus_id, line, time) 

	print(buses)
	next_download = time() + DOWNLOAD_INTERVAL

	
def daemon():
	if time() > next_download:
		theading.Thread(target="download")
	if time() > next_display:
		pass
		# have a current buses counter
		# increment by one
		# display from ordered list of next buses
	
	
	
def main():
	print("bunny")
	#device = led.sevensegment(cascaded=2)
	#device.write_text(1,"BUSES")
	download()
	daemon_thread = threading.Thread(target="daemon", args=(device,))
	daemon_thread.setDaemon(True)
	daemon_thread.start()
	

if __name__ == '__main__':
	main()