import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import csv
import threading

# Variables provided in ../.env . Defaults to 200nm around London (England)
LAT = os.getenv('FEEDER_LAT', '51.5072')
LON = os.getenv('FEEDER_LONG', '0.1276')
DST = os.getenv('HELIWATCH_RAD_NAUTICAL_MILES', '200')

SQUAWKS = {}
ICAO = []

# ADSBFI API provides the HEX code of the aircrafts within a certain radius of the given coordinates
ADSBFI = "https://opendata.adsb.fi/api/v2/lat/" + str(LAT) + "/lon/" + str(LON) + "/dist/" + str(DST)
HEX = ""
REG = ""

# HEXDB API provides information on the owner (among other things) of the queried aircraft (in this case a heli)
HEXDB = "https://hexdb.io/api/v1/aircraft/"
OWNER = ""

SQUAWK = ""

def identify_nearest_heli(aircrafts):
    return [item for item in aircrafts if 'hex' in item and 't' in item and item.get('t') in ICAO]

# Create HTTP Server to publish data required for the Rainmeter skin
class HandlerA(BaseHTTPRequestHandler):
    def do_GET(self):
        global HEX
        global OWNER
        global SQUAWK
        global REG
        self.send_response(200)
        self.end_headers()
        data = requests.get(url=ADSBFI).json()
        aircrafts = data["aircraft"]
        if aircrafts:
            aircrafts.sort(key=lambda x: x["dst"])
            nearest_heli = identify_nearest_heli(aircrafts)
            if nearest_heli:
                if 'hex' in nearest_heli[0] and not nearest_heli[0]['hex'] == HEX:
                    HEX = nearest_heli[0]['hex']
                    SQUAWK = ""
                    if 'squawk' in nearest_heli[0]:
                        SQUAWK=SQUAWKS.get(nearest_heli[0]['squawk'])
                        if SQUAWK is None:
                            SQUAWK=""
                    if 'r' in nearest_heli[0] and not nearest_heli[0]['r'] == REG:
                        REG = nearest_heli[0]['r']
                    owner = requests.get(url=HEXDB + HEX).json().get('RegisteredOwners')
                    if owner:
                        OWNER = owner
                        if OWNER== "Private":
                            message = f"Private {HEX}\n{SQUAWK}"
                        else:
                            message = f"{HEX} {OWNER}\n{SQUAWK}"
                        self.wfile.write(message.encode('utf-8'))
                    else:
                        message = f"{HEX} not in HEXDB\n{SQUAWK}"
                        self.wfile.write(message.encode('utf-8'))
                else:
                    message = f"{HEX} {OWNER}\n{SQUAWK}"
                    self.wfile.write(message.encode('utf-8'))
            else:
                message = f"Not a Heli {HEX}\n{SQUAWK}"
                self.wfile.write(message.encode('utf-8'))
        else:
            self.wfile.write("Aircraft Free Zone".encode('utf-8'))

# Create HTTP Server that redirects to the Flightradar24 entry of the nearest aircraft
class HandlerB(BaseHTTPRequestHandler):
    def do_GET(self):
        if REG:
            target = "https://www.flightradar24.com/data/aircraft/" + str(REG)
            try:
                r = requests.get(target, allow_redirects=True)
                print(target)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Error contacting FR24")
                return

            final_url = r.url

            if final_url.rstrip("/") == "https://www.flightradar24.com/data/aircraft":
                self.send_response(302)
                self.send_header("Location", final_url)
                self.end_headers()
                self.wfile.write(b"No FR24 Entry")
            else:
                self.send_response(302)
                self.send_header("Location", final_url)
                self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Aircraft Free Zone'.encode('utf-8'))

def run_server(port, handler):
    server = HTTPServer(("127.0.0.1", port), handler)
    server.serve_forever()

if __name__ == "__main__":
    with open('squawks.csv', mode='r') as file:
         squawks_csv = csv.DictReader(file)
         for row in squawks_csv:
             SQUAWKS.update({row.get('squawk'): row.get('function')})

    with open('icao.csv', mode='r') as file:
        for row in file:
            ICAO.append(row.strip())
    t1 = threading.Thread(target=run_server, args=(8003, HandlerA))
    t2 = threading.Thread(target=run_server, args=(8004, HandlerB))
    t1.start()
    t2.start()