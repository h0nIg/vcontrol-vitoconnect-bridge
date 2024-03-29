#!/usr/bin/env python3
import threading
import queue
import os
import serial
import time
import socket
import socketserver

requests = queue.Queue()
response_vitoconnect = queue.Queue()
response_proxy = queue.Queue()

## open devices
ser_heating = serial.Serial("/dev/ttyUSB0",
                     baudrate=4800,
                     parity=serial.PARITY_EVEN,
                     stopbits=serial.STOPBITS_TWO,
                     bytesize=serial.EIGHTBITS,
                     timeout=1)
ser_vitoconnect = serial.Serial("/dev/ttyAMA0",
                     baudrate=4800,
                     parity=serial.PARITY_EVEN,
                     stopbits=serial.STOPBITS_TWO,
                     bytesize=serial.EIGHTBITS,
                     timeout=1)

def read(s, bytes):
    try:
        return s.read(bytes)
    except AttributeError:
        return s.recv(bytes)

def write(s, bytes):
    try:
        return s.write(bytes)
    except AttributeError:
        return s.send(bytearray(bytes))

def flush(s):
    try:
        s.flushInput
    except AttributeError:
        pass

def printbytes(type, bytes):
    if bytes:
        print (type, end="")
        print (" ", end="")
        for c in bytes:
            print("%02x " % c, end="")
        print()
    else:
      print(type)

def addrequest(s, name, responsequeue):
    while True:
        try:
            header = s.read(1)
            if not header:
                continue
        except AttributeError:
            header = s.recv(1)
            if not header:
                break

        #printbytes(name + " REQ HEADER", header)
        if header == bytes([0x04]):
            print(name + " P300 RESET")
            write(s, [0x05])
        elif header == bytes([0x16]):
            p300 = read(s, 2)
            if p300 != bytes([0x00, 0x00]):
                flush(s)
                continue

            print(name + " P300 START")
            write(s, [0x06])
        else:
            lenbyte = read(s, 1)
            if not lenbyte:
                continue

            len = int.from_bytes(lenbyte, byteorder='little') + 1
            msg = header + lenbyte + read(s, len)

            #printbytes(name + " REQ BODY", msg)

            with responsequeue.mutex:
                responsequeue.queue.clear()

            requests.put({"name": name, "msg": msg, "queue": responsequeue})

            try:
                response = responsequeue.get(block=True, timeout=1)
                responsequeue.task_done()
                write(s, response)
            except queue.Empty:
                print(name + "no response within 1 second")

def sendrequest(s):
    init = False

    while True:
        if init == False:
            print("INIT")

            # maybe something broken and timeout has happened reading from heating
            # still a response in buffer?
            s.flushInput()

            # reset
            time.sleep(10)
            s.write([0x04])

            while True:
                initR = s.read(1)
                # optolink periodically sends x05 every 2 seconds
                if initR:
                    printbytes("INIT", initR)

                    # heater reset, time for sync required
                    if initR == bytes([0xFF]):
                        time.sleep(10)
                        continue

                    # we have an init responsn
                    if initR == bytes([0x06]):
                        s.flushInput()
                        break
                else:
                    # hammer until we have a successful session
                    print("P300 KEEPALIVE")
                    s.write([0x16, 0x00, 0x00])

            init = True
            print("INIT DONE")

        try:
            request = requests.get(True, 1)
        except queue.Empty:
            print("REQ KEEPALIVE")

            s.flushInput()
            s.write([0x16, 0x00, 0x00])

            keepR = s.read(1)
            if not keepR or keepR != bytes([0x06]):
                printbytes("REQ KEEPALIVE FAIL", keepR)
                init = False

            continue

        requests.task_done()
        if request['msg']:
            start_time = time.strftime("%d.%m.%Y %H:%M:%S")

            #print(request['name'],  end="")
            #print(" ", end="")
            #print(start_time, end="")
            #print(" ", end="")

            #for c in request['msg']:
            #    print("%02x " % c, end="")
            #print()

            s.flushInput()

            s.write(request['msg'])
            header = s.read(2)
            #printbytes("RESP HEADER", header)
            lenbyte = s.read(1)
            if not lenbyte:
                print("INIT REQUIRED 2?")
                init = False
                continue

            #printbytes("RESP LEN", lenbyte)
            len = int.from_bytes(lenbyte, byteorder='little') + 1
            msg = s.read(len)
            if not msg:
                print("INIT REQUIRED 3?")
                init = False
                continue

            #printbytes("RESP BODY", msg)

            request['queue'].put(header + lenbyte + msg)


thread1 = threading.Thread(target=addrequest, args=(ser_vitoconnect, "vitoconnect", response_vitoconnect,),)
thread2 = threading.Thread(target=sendrequest, args=(ser_heating,),)

print('START')

thread2.start()
thread1.start()

class ThreadedTCPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        addrequest(self.request, "proxy" + str(self.client_address[1]), response_proxy)

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    pass

server = ThreadedTCPServer(('127.0.0.1', 12345), ThreadedTCPRequestHandler)

server_thread = threading.Thread(target=server.serve_forever)
server_thread.daemon = True
server_thread.start()

print('STARTED')

server_thread.join()
