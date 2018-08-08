import threading
import json
import requests
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from os import path

from gpiozero import MotionSensor, Button

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.virtual import sevensegment

PIR_GPIO = 14
LEFT_BUTTON_GPIO = 17
RIGHT_BUTTON_GPIO = 26

BUS_STOP_ID = "490006045W"  # Stratford Park
POINT = "/arrivals"
API_URI = "https://api.tfl.gov.uk/StopPoint/" + BUS_STOP_ID + POINT

DOWNLOAD_INTERVAL = 45  # download every 45 seconds
# Note: was 30 seconds, but TfL docs say data is cached for 30
# so "there is no benefit to the developer in querying any 
# of the data services any more frequently"
last_download = 0

DISPLAY_INTERVAL = 5 # show each bus for this many seconds

WAKE_TIME = 100  # stay awake for 1m 40s

MAX_CUT_OFF = 20 * 60   # ignore buses more than 20 minutes away
MIN_CUT_OFF = 60  # ignore buses less than 1 minute away

class Bus:
    def __init__(self, id, line, expected):
        self.id = id
        self.line = line
        self.expected = expected

buses = []

def download_work(prev_timestamp):
    logging.debug("Starting a download")
    global buses, last_download
    # get the bus stop arrivals data from the TFL API
    response = requests.get(API_URI, timeout=5)
    # this will raise an exception if the response is not 200
    response.raise_for_status()
    json_data = response.json()  # TFL API returns a list
    logging.debug(json_data)
    # clear out the previous list of buses
    if len(json_data) == 0:
        return prev_timestamp
    # process the json data to pull out just the interesting items
    timestamp = json_data[0]["timestamp"]
    if timestamp != prev_timestamp:
        last_download = time.time()
        buses.clear()
        for foo in json_data:
            bus_id = foo["vehicleId"]
            line = foo["lineName"]
            expected = foo["timeToStation"]
            print(line, expected)
            buses.append(Bus(bus_id, line, expected))
        print()
    else:
        print("Found same timestamp, skipping")
    return timestamp

def download(prev_timestamp):
    try:
        timestamp = download_work(prev_timestamp)
        timer_thread = threading.Timer(DOWNLOAD_INTERVAL, download, (timestamp,))
        timer_thread.start()
    except Exception as e:
        logging.exception(e)
        # wait only 10 secs if there was an issue
        quicker_thread = threading.Timer(10, download, (prev_timestamp,))
        quicker_thread.start()

def button_listener_work():
    #left = Button(LEFT_BUTTON_GPIO)
    right = Button(RIGHT_BUTTON_GPIO)
    print("button listener thread")
    #right.when_pressed = right_func
    while True:
        #if right.is_pressed:
        right.wait_for_press()
        print("Right on!")
        print("Thread count = ", threading.enumerate())
        time.sleep(3)

def button_listener():
    try:
        button_listener_work()
    except e:
        logging.exception(e)

# a little helper function to handle calcuating the length of a time str
# with a dot in it which does not count to the length as far as our
# sevenseg display is concerned
def tlen(time_str):
    return len(time_str) - time_str.count(".")


def display_buses(seg):
    global buses, last_download
    # calculate how long ago the last download was
    diff = time.time() - last_download
    sorted_buses = sorted(buses, key=lambda bus: bus.expected)
    expected_times = []
    # iterate through bus data and store strings for display
    for bus in sorted_buses:
        expected = round(bus.expected - diff)
        if expected < MIN_CUT_OFF or expected > MAX_CUT_OFF:
            continue
        mins = expected // 60
        # first bus we *may* want minutes and seconds
        # so check if this is the first bus
        if len(expected_times) == 0:
            # now only if < 10 minutes
            if mins < 10:
                secs = str(expected % 60)
                if len(secs) == 1:
                    secs = "0" + secs
                #expected_times.append(str(mins) + "." + secs + " ")
                expected_times.append(str(mins) + "." + secs)
            else:
                #expected_times.append(str(mins) + " ")
                expected_times.append(str(mins))
        # other buses just use miuntes
        else:
            expected_times.append(mins)

    # now iterate though the data to be displayed
    if len(expected_times) == 0:
        seg.text = "ZERO BUS"
        buses = []
    else:
        # different display behaviour based on the times of the
        # upcoming buses i.e how many can we fit on
        if len(expected_times) == 1:
            seg.text = expected_times[0]
        else:
            t1 = expected_times[0]
            t2 = str(expected_times[1])
            pad = " "*(8 - tlen(t1+t2))
            # if the second bus is only a single digit time then
            # squeeze the third bus on to the display
            if len(expected_times) >= 3 and len(t2) == 1:
                t3 = str(expected_times[2])
                pad = " "*(3 - tlen(t3))
                seg.text = t1 + pad + t2 + " " + t3
            else:
                seg.text = t1 + pad + t2
        time.sleep(1)


def daemon_work(seg, pir):
    logging.debug("Now in daemon")
    global buses
    #last_download = 0
    #next_download = 0

    sleepy_time = time.time() + WAKE_TIME
    while True:
        if time.time() > sleepy_time:
            # go to sleep
            seg.device.hide()
            pir.wait_for_motion()
            # blocks until the sensor is activated
            seg.device.show()
            sleepy_time = time.time() + WAKE_TIME
        if len(buses) == 0:
            seg.text = "ZERO BUS"
            time.sleep(DISPLAY_INTERVAL)
        else:
            display_buses(seg)


def daemon(seg, pir):
    try:
        daemon_work(seg, pir)
    except e:
        logging.exception(e)


def main():
    try:
        location = path.realpath(__file__).rpartition("/")[0]
        logfile = location + "/log_tfl.txt"
        trfh = TimedRotatingFileHandler(logfile, when="midnight", backupCount=1)
        #logging.basicConfig(filename="log_tfl.txt", format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.DEBUG)
        logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.DEBUG, handlers=[trfh])
        logging.debug("Location = " + location)
        logging.debug("File = " + __file__)
        serial = spi(port=0, device=0, gpio=noop())
        device = max7219(serial, cascaded=1)
        seg = sevensegment(device)
        pir = MotionSensor(PIR_GPIO)
        daemon_thread = threading.Thread(target=daemon, args=(seg, pir,))
        #daemon_thread.setDaemon(True)
        logging.debug("Starting daemon")
        daemon_thread.start()
        download(0)
        button_thread = threading.Thread(target=button_listener)
        button_thread.start()
    except Exception as e:
        logging.exception(e)
        raise

if __name__ == '__main__':
    main()
