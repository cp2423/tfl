import threading
import json
import requests
import time
import logging
from os import path

from gpiozero import MotionSensor

from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.virtual import sevensegment

# TODO the ID and key are not actually used. can you ditch this code!?
basepath = path.dirname(__file__)
filepath = path.abspath(path.join(basepath, "..", "tfl.conf"))
with open(filepath) as conf:
    # auth tokens for my dev account with TFL
    # NB TFL username is cp---3 registered with teach first email addr
    APP_ID = "8717f35a"
    APP_KEY = conf.readline()
    print(APP_KEY)

PIR_GPIO = 14

BUS_STOP_ID = "490006045W"  # Stratford Park
POINT = "/arrivals"
API_URI = "https://api.tfl.gov.uk/StopPoint/" + BUS_STOP_ID + POINT

DOWNLOAD_INTERVAL = 45  # download every 45 seconds
# Note: was 30 seconds, but TfL docs say data is cached for 30
# so "there is no benefit to the developer in querying any 
# of the data services any more frequently"

DISPLAY_INTERVAL = 5 # show each bus for this many seconds

WAKE_TIME = 100  # stay awake for 1m 40s

class Bus:
    def __init__(self, id, line, expected):
        self.id = id
        self.line = line
        #self.arrives = arrives
        self.expected = expected

buses = []

def download():
    logging.debug("Starting a download")
    global buses
    # get the bus stop arrivals data from the TFL API
    response = requests.get(API_URI)
    if response.status_code != 200:
        # TODO how to handle errors??
        return
    logging.debug(response.status_code)
    json_data = response.json()  # TFL API returns a list
    #print(json_data)

    # clear out the previous list of buses
    if len(json_data) == 0:
        return
    buses.clear()
    # process the json data to pull out just the interesting items
    for foo in json_data:
        bus_id = foo["vehicleId"]
        line = foo["lineName"]
        #arrives = foo["timeToStation"]
        #buses[arrives] = Bus(bus_id, line, arrives)
        #expected = foo["expectedArrival"]
        expected = foo["timeToStation"]
        print(line, expected)
        buses.append(Bus(bus_id, line, expected))

    #print(buses)


def daemon(seg, pir):
    logging.debug("Now in daemon")
    global buses
    last_download = 0
    next_download = 0
    CUT_OFF = 59 * 60   # ignore buses more than 59 minutes away

    sleepy_time = 0
    while True:
        if time.time() > sleepy_time:
            # go to sleep
            seg.device.hide()
            pir.wait_for_motion()
            # blocks until the sensor is activated
            seg.device.show()
            sleepy_time = time.time() + WAKE_TIME
        logging.debug("bunny")
        if len(buses) == 0:
            seg.text = "ZERO BUS"
            time.sleep(5)
            pass
        else:
            # calculate how long ago the last download was
            diff = time.time() - last_download
            sorted_buses = sorted(buses, key=lambda bus: bus.expected)
            expected_times = []
            for bus in sorted_buses:
                expected = round(bus.expected - diff)
                if expected > CUT_OFF:
                    continue
                mins = str(expected // 60)
                secs = str(expected % 60)
                if len(secs) == 1:
                    secs = "0" + secs
                expected_times.append(mins + "." + secs)
            if len(expected_times) == 0:
                seg.text = "ZERO BUS"
                buses = []
            else:
                pad0 = 5 - len(expected_times[0])
                first_time = " "*pad0 + expected_times[0]
                if len(expected_times) == 1:
                    expected_times.append(".")  # throw in a blank
                for expected_time in expected_times[1:]:
                    pad1 = 5 - len(expected_time)
                    other_time = " "*pad1 + expected_time
                    seg.text = first_time + other_time
                    time.sleep(5)
        logging.debug(time.time())
        if time.time() > next_download:
            logging.debug("Bong!")
            download_thread = threading.Thread(target=download)
            download_thread.start()
            last_download = time.time()
            next_download = time.time() + DOWNLOAD_INTERVAL


def main():
    try:
        logging.basicConfig(filename="log_tfl.txt", format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.DEBUG)
        serial = spi(port=0, device=0, gpio=noop())
        device = max7219(serial, cascaded=1)
        seg = sevensegment(device)
        #seg.text = "BUSES"
        #download()
        pir = MotionSensor(PIR_GPIO)
        daemon_thread = threading.Thread(target=daemon, args=(seg, pir,))
        #daemon_thread.setDaemon(True)
        logging.debug("Starting daemon")
        daemon_thread.start()
    except Exception as ex:
        logger.exception(ex)
        raise

if __name__ == '__main__':
    main()
