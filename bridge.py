#!/usr/bin/env python3
import threading
import queue
import os
import serial
import time
import socket

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

def addrequest(s, name, responsequeue):
    while True:
        header = read(s, 1)
        if not header:
            continue

        printbytes("REQ HEADER", header)
        if header == bytes([0x04]):
            print("P300 RESET")
            write(s, [0x05])
        elif header == bytes([0x16]):
            p300 = read(s, 2)
            if p300 != bytes([0x00, 0x00]):
                flush(s)
                continue

            print("P300 START")
            write(s, [0x06])
        else:
            lenbyte = read(s, 1)
            if not lenbyte:
                continue

            len = int.from_bytes(lenbyte, byteorder='little') + 1
            msg = header + lenbyte + read(s, len)

            printbytes("REQ BODY", msg)

            with responsequeue.mutex:
                responsequeue.queue.clear()

            requests.put({"name": name, "msg": msg, "queue": responsequeue})

            try:
                response = responsequeue.get(block=True, timeout=1)
                responsequeue.task_done()
                write(s, response)
            except queue.Empty:
                print("no response within 1 second")

def sendrequest(s):
    init = False

    while True:
        if init == False:
            print("INIT")

            # maybe something broken and timeout has happened reading from heating
            # still a response in buffer?
            s.flushInput()

            # reset
            s.write([0x04])

            while True:
                initR = s.read(1)
                # optolink periodically sends x05 every 2 seconds
                if initR:
                    printbytes("INIT", initR)

                    # we have a response which is not "not initialized"
                    if initR != bytes([0x05]):
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
            # any dummy command to keep connection alive
            s.write([0x41, 0x05, 0x00, 0x61, 0x00, 0xf8, 0x01, 0x5f])

            continue

        requests.task_done()
        if request['msg']:
            start_time = time.strftime("%d.%m.%Y %H:%M:%S")

            print(request['name'],  end="")
            print(" ", end="")
            print(start_time, end="")
            print(" ", end="")

            for c in request['msg']:
                print("%02x " % c, end="")
            print()

            s.flushInput()

            s.write(request['msg'])
            header = s.read(2)
            printbytes("RESP HEADER", header)
            lenbyte = s.read(1)
            if not lenbyte:
                print("INIT REQUIRED 2?")
                init = False
                continue

            printbytes("RESP LEN", lenbyte)
            len = int.from_bytes(lenbyte, byteorder='little') + 1
            msg = s.read(len)
            if not msg:
                print("INIT REQUIRED 3?")
                init = False
                continue

            printbytes("RESP BODY", msg)

            request['queue'].put(header + lenbyte + msg)


thread1 = threading.Thread(target=addrequest, args=(ser_vitoconnect, "vitoconnect", response_vitoconnect,),)
thread2 = threading.Thread(target=sendrequest, args=(ser_heating,),)

print('START')

thread2.start()
thread1.start()

port = 12345
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(("127.0.0.1", port))

# put the socket into listening mode
s.listen(5)

print('STARTED')

# a forever loop until client wants to exit
while True:

    # establish connection with client
    c, addr = s.accept()

    print('Connected to :', addr[0], ':', addr[1])

    # Start a new thread and return its identifier
    threadc = threading.Thread(target=addrequest, args=(c, "proxy" + str(addr[1]), response_proxy,),)
    threadc.start()

s.close()
