# --------------------------------------------------------------------------------------------- 
#                                                                                               
#   University of North Texas                                                                   
#   Department of Electrical Engineering                                                        
#                                                                                               
#   Faculty Advisors:   Dr. Xinrong Li, Dr. Jesse Hamner, Dr. Song Fu
#   Name:               Ovie Onoriose                                                           
#                                                                                            
#   Title:              Traffic occupancy data collecting client                                
#   Version:            6.2                                                                  
#                                                                                               
#   Description:                                                                                
#       This script sends a probe request on the Xbee connected to the Raspberry Pi
#       to find all other active Xbee's (connected to sensor nodes) on the network
#       It then proceeds to send requests and store the received data from each node
#       sequentially. This received data is stored in a local SQlite database 
#                                                                                               
#   Dependencies:                                                                               
#       Python 3.5.1, sqlite3, numpy, scipy
#
#   Change Log:
#       v6.2 (08/10/2017)
#            program now stores background levels and the standard deviation of each grid
#       v6.1.2 ((03/01/2017)
#           added trigger column to database if a pixel is higher than a certain
#           threshold
#       v6.1 (01/22/2017)                                                                       
#           In the case that a node loses power or otherwise becomes unresponsive,            
#           Node discovery is performed to repopulate the list of active nodes so             
#           the program doesn't hang while trying to receive input                            



import serial
import sqlite3
import datetime
import time
from collections import Counter
import atexit
from copy import copy
import numpy as np

# open serial port and connect to database

# ser = serial.Serial("/dev/ttyAMA0",115200,timeout = 350) #open serial port for RPi
ser = serial.Serial('COM3', 115200, timeout=350)  # open serial port

conn = sqlite3.connect('occupancy.db')  # connect to the database
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS data"
          " (Node real, Datetime text, Grideye text, Trigger int, CO2PPM real, Temperature real,"
          " Humidity real, PIR real)")
c.execute("CREATE TABLE IF NOT EXISTS background"
          " (Node integer PRIMARY KEY, Datetime text, Background text, Sample integer, Mean text, SumSqDif text)")

node_list = []
# get background data from database
c.execute('SELECT Node, Background FROM background')
background = []
for t in c.fetchall():
    background.append([t[0], [float(i) for i in t[1].split(',')]])

# get standard deviations from database
c.execute('SELECT Node, SumSqDif FROM background')
sum_sq_dif = []
for t in c.fetchall():
    sum_sq_dif.append([t[0], [float(i) for i in t[1].split(',')]])

# get means from database
c.execute('SELECT Node, Mean FROM background')
bg_mean = []
for t in c.fetchall():
    bg_mean.append([t[0],  [float(i) for i in t[1].split(',')]])

# get count for std dev from database
c.execute('SELECT Node, Sample FROM background')
s = []
for t in c.fetchall():
    s.append(list(t))


grideye = [0.] * 64
scaled_bg = [0.] * 64
delta1 = [0.] * 64
delta2 = [0.] * 64


class MyList(list):
    def __repr__(self):
        return '[' + ', '.join("0x%X" % x if type(x) is int else repr(x) for x in self) + ']'


def remove_node_dupes(x):
    count = Counter((i[1]) for i in x)
    while len([i for i in x if count[(i[1])] > 1]) > 1:
        x.remove(max([i for i in x if count[(i[1])] > 1]))
        count = Counter((i[1]) for i in x)


def find_checksum(packet):  # find checksums of Xbee packets
    total = 0
    for i in range(3, len(packet)):
        total += packet[i]
    return 0xFF - (0xFF & total)


def stop_data():
    print('stop_data has started')
    ser.flushInput()
    ser.flushOutput()
    print('stop_data has cleared serial port')
    time.sleep(.1)
    end_data = [0x7E, 0x00, 0x10, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFE,
                0x02, 0x44, 0x31, 0x04, 0x72]
    ser.write(end_data)
    print('stop_data has sent stop request')


def discovery():

    # reset serial buffers
    ser.flushInput()
    ser.flushOutput()
    time.sleep(.1)
    # send out broadcast requesting serials of all nodes on network
    node_request = [0x7E, 0x0, 0xF, 0x17, 0x1, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0xFF, 0xFF, 0xFF, 0xFE, 0x2, 0x73,
                    0x6C, 0xB]  # checksum is already here

    ser.write(node_request)
    time.sleep(5)
    # received packets from nodes should be 23 bytes each
    nodes = int(ser.in_waiting/23)
    if nodes == 0:
        print('no nodes discovered')
        discovery()
        return
    del node_list[:]

    for i in range(nodes):
        a = ser.read()
        a = int.from_bytes(a, byteorder='big')
        if a != 0x7E:  # check starting bit, discarding if wrong
            discovery()
            return
        l = ser.read(2)
        l = int.from_bytes(l, byteorder='big')
        b = ser.read()
        b = int.from_bytes(b, byteorder='big')
        if b != 0x97:  # check if this is indeed a node identification packet
            discovery()
            return
        data = ser.read(l)
        node_address = tuple(data[14:18])
        node_list.append((i, node_address))
        print('node discovered. address:{0}'.format(MyList(list(node_address)),))
        remove_node_dupes(node_list)


# def data_request(serial_low):
#     ser.flushInput()
#     ser.flushOutput()
#     # time.sleep(.1)
#     # reset pin interrupt on launchpad
#     request_end = [0x7E, 0x00, 0x10, 0x17, 0x00, 0x00, 0x13, 0xA2, 0x00] + list(serial_low) + \
#                   [0xFF, 0xFE, 0x02, 0x44, 0x31, 0x04]  # packet without checksum
#     request_end.append(find_checksum(request_end))  # append checksum to packet
#     ser.write(request_end)
#     time.sleep(0.1)
#     # Request for data  for testing I'm sending test, the final thing to send is currently commented
#     # toggles pin interrupt
#     request = [0x7E, 0x00, 0x10, 0x17, 0x00, 0x00, 0x13, 0xA2, 0x00] + list(serial_low) + \
#               [0xFF, 0xFE, 0x02, 0x44, 0x31, 0x05]  # packet without checksum
#     request.append(find_checksum(request))  # append checksum to packet
#     ser.write(request)
#     print('requesting data from {0}\n'.format(MyList(list(serial_low)),))
#     return


def data_request():
    ser.flushInput()
    ser.flushOutput()
    # time.sleep(.1)
    # reset pin interrupt on launchpad
    request_end = [0x7E, 0x00, 0x10, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF] + \
                  [0xFF, 0xFE, 0x02, 0x44, 0x31, 0x04]  # packet without checksum
    request_end.append(find_checksum(request_end))  # append checksum to packet
    ser.write(request_end)
    time.sleep(0.1)
    # Request for data  for testing I'm sending test, the final thing to send is currently commented
    # toggles pin interrupt
    request = [0x7E, 0x00, 0x10, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF] + \
              [0xFF, 0xFE, 0x02, 0x44, 0x31, 0x05]  # packet without checksum
    request.append(find_checksum(request))  # append checksum to packet
    ser.write(request)
    print('requesting data')
    return


def read_packet():
    a = ser.read(1)
    if len(a) == 0:
        print('no data received. rediscovering nodes...\n')
        return 1  # if no data is read, return 1 (Run discovery and restart at beginning of node_list)
    elif int.from_bytes(a, byteorder='big') != 0x7E:  # check starting bit, discarding if wrong
        read_packet()
        return 0
    l = ser.read(2)
    l = int.from_bytes(l, byteorder='big')  # calculate length of packet
    b = ser.read(1)
    b = int.from_bytes(b, byteorder='big')
    print('data type is {0}'.format(MyList([b]),))
    if b == 0x90:
        data_store(l)
    else:
        data = ser.read(l)
        print('------------invalid data\n')
        print(MyList(list(data)))
    if ser.in_waiting > 0:
        read_packet()
        return 0


def data_store(l):
    data = ser.read(l)  # read rest of packet
    print('data received:')
    print(MyList(list(data)))
#    print('\n')

    trigger = 0
    # Break data into more manageable sections
    # sixty four source address=data[0:7]
    # sixteen source address=data[8:9]
    # receive options address=data[10]
    # rf_data = data[11:l - 1]

    if data[11] == 0xDF:
        inactive_bg(data)

    elif data[11] == 0xEF:
        active_bg(data)

    else:
        node = data[11]
        co2 = (data[12] * 200)
        humid = ((data[13] << 8) | data[14]) / 10
        temp = ((data[15] << 8) | data[16]) / 10
        pir = data[17]
        for i in range(64):
            grideye[i] = (((data[2 * i + 18] << 8) | data[2 * i + 19]) / 4)
            if grideye[i] > 25:
                trigger = 1

        # map grideye data to a string for simplicity in entering them into the database
        grid_str = ','.join(map(str, grideye))

        # finds the time
        current = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S:%f")

        # insert data into database
        c.execute("INSERT INTO data"
                  " (Node, Datetime, Grideye, Trigger, CO2PPM, Temperature, Humidity, PIR)"
                  " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (node, current, grid_str, trigger, co2, temp, humid, pir))
        conn.commit()


def inactive_bg(packet):
    node = packet[12]
    for i in range(64):
        grideye[i] = (((packet[2 * i + 14] << 8) | packet[2 * i + 15]) / 4)

    # update the thermal background, or create a new entry if a background doesn't exist
    try:
        bg_index = [i[0] for i in background].index(node)
        for i in range(64):
            background[bg_index][1][i] = 0.95 * background[bg_index][1][i] + 0.05 * grideye[i]
        print('background try success')
    except ValueError:
        background.append([node, copy(grideye)])
        bg_index = [i[0] for i in background].index(node)
        print('background try fail')
    bg_str = ','.join(map(str, background[bg_index][1]))
    print('background updated\n')

    # incrementing a counter to use to calculate mean and variance/std dev
    try:
        bg_index = [i[0] for i in s].index(node)
        s[bg_index][1] += 1
        print('sample try success')
    except ValueError:
        s.append([node, 1])
        bg_index = [i[0] for i in s].index(node)
        print('sample try fail')
    s_int = s[bg_index][1]
    print('grideye')
    print(grideye)

    # update the mean for each grid position to calculate the std dev
    try:
        bg_index = [i[0] for i in bg_mean].index(node)
        for i in range(64):
            delta1[i] = grideye[i] - bg_mean[bg_index][1][i]
            bg_mean[bg_index][1][i] += (delta1[i]/s[bg_index][1])
        print('mean try success')
    except ValueError:
        bg_mean.append([node, copy(grideye)])
        bg_index = [i[0] for i in bg_mean].index(node)
        print('mean try fail')
    bg_mean_str = ','.join(map(str, bg_mean[bg_index][1]))
    print('delta1')
    print(delta1)
    print('bg_mean')
    print(bg_mean[bg_index][1])

    # update the sum of squared differences for each grid position to calculate the threshold
    # to get actual standard deviation, calculate sqrt(sum_sq_dif/s-1)
    try:
        bg_index = [i[0] for i in sum_sq_dif].index(node)
        for i in range(64):
            delta2[i] = grideye[i] - bg_mean[bg_index][1][i]
            sum_sq_dif[bg_index][1][i] += (delta1[i] * delta2[i])
        print('sumsqdif try success')
    except ValueError:
        sum_sq_dif.append([node, [0.] * 64])
        bg_index = [i[0] for i in sum_sq_dif].index(node)
        print('sumsqdif try fail')
    sum_sq_dif_str = ','.join(map(str, sum_sq_dif[bg_index][1]))
    print('delta2')
    print(delta2)

    current = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S:%f")
    c.execute("REPLACE INTO background"
              " (Node, Datetime, Background, Sample, Mean, SumSqDif)"
              " VALUES (?, ?, ?, ?, ?, ?)", (node, current, bg_str, s_int, bg_mean_str, sum_sq_dif_str))
    conn.commit()
    print('inactive background update complete')


def active_bg(packet):
    node = packet[12]
    for i in range(64):
        grideye[i] = (((packet[2 * i + 14] << 8) | packet[2 * i + 15]) / 4)
    try:
        bg_index = [i[0] for i in background].index(node)
        print('active backgroudn try sucess')
    except ValueError:
        print('active background update failed\n')
        return

    # Finding the 5 lowest temperatures to modify background on
    location = [66] * 5
    minimum = grideye[0]
    for i in range(5):
        for m in range(64):
            k = 0
            for j in range(5):
                if m == location[j]:
                    k = 1
            if k == 0 and grideye[m] < minimum:
                minimum = grideye[m]
                location[i] = m
        if location[i] == i:
            minimum = grideye[i + 1]
        else:
            minimum = grideye[0]

    bg_scale = sum([background[bg_index][1][i]/grideye[i] for i in location])/5
    for i in range(64):
        # scaled_bg[i] = bg_scale * grideye[i]
        background[bg_index][1][i] = 0.99 * background[bg_index][1][i] + 0.01 * bg_scale * grideye[i]

    current = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S:%f")
    bg_str = ','.join(map(str, background[bg_index][1]))
    c.execute("REPLACE INTO background"
              " (Node, Datetime, Background, Sample, Mean, SumSqDif)"
              " VALUES (?, ?, ?, (SELECT Sample FROM background WHERE Node = ?),"
              " (SELECT Mean FROM background WHERE Node = ?),"
              " (SELECT SumSqDif FROM background WHERE Node = ?))", (node, current, bg_str, node, node, node))
    conn.commit()
    print('active background update complete')

atexit.register(stop_data)
# run indefinitely
while True:
    # discovery()
    # for j in node_list:
    #     data_request(j[1])
    data_request()
    while True:
        if read_packet():   # if data request returns 1, start over at while loop after discovery
            break
        else:
            print('loop starting over\n')
