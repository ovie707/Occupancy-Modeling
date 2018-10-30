# --------------------------------------------------------------------------------------------- 
#                                                                                               
#   University of North Texas                                                                   
#   Department of Electrical Engineering                                                        
#                                                                                               
#   Faculty Advisors:   Dr. Xinrong Li, Dr. Jesse Hamner, Dr. Song Fu
#   Name:               Ovie Onoriose                                                           
#                                                                                                                                                                       
#   Title:              TrafficAlgorithm                                 
#   Version:            2.3                                                                  
#                                                                                               
#   Description:                                                                                
#       This script takes data collected by the nodes and stored in the occupancy
# 		database and analyzes it, calculating different features about the objects
# 		that move through the measurement area. It then stores this analyzed information in
# 		a new table in the database.
#                                                                                               
#   Dependencies:                                                                               
#       Python 3.5.1, sqlite3, numpy
#
# changes for v0-3:
# threshold is now based on readings from the sensor node
# calculating a moving average and std dev of each pixel individually
# threshold is the thermal background plus 3 times the std dev
#
# changes for v1-0:
# algorithm now outputs the times when a "hotspot" was present
#
# changes for v2-1:
# plot now shows 1-d timeline of blobs found
# direction of overall movement of each blob is calculated and displayed. (0 to 360 degrees)
#
# changes for v2-2:
# centroid prediction
#
# changes for v2-3
# centroid prediction is calculated using an exponentially weighted average of velocities instead of just the previous
# blobs are now paired with the hotspots that are closest to their predicted location, instead of just being paired with
# the first one found in range


from queue import Queue
import numpy as np
from scipy import optimize as op
from matplotlib import pyplot as plt
from matplotlib import dates as mdates
import sqlite3
from copy import copy
import datetime as dt
import math
from operator import add

node = 2

conn = sqlite3.connect('occupancy.db')

c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS blobs "
          "(TimeStart text, TimeEnd text, Times text, Readings integer, Duration real, AvgSize real, AvgTemp real, "
          "Displacement real, Centroids text, AvgBearing real, Bearings text, "
          "AvgVelocity real, Velocities text, Predictions text) ")

start = input("Starting date/time (Format: YYYY-MM-DDTHH:mm:ss) (enter 'all' to take all measurements): ")
if start == 'all':
    c.execute('SELECT Grideye FROM data')
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data')
    datetime_data = c.fetchall()
    c.execute('SELECT Temperature FROM data')
    temp_data = c.fetchall()
    c.execute('SELECT Humidity FROM data')
    humidity_data = c.fetchall()
elif start == 'test':
    start = '2017-11-15T11:38'
    end = '2017-11-15T17:38'
    # start = '2017-12-11T12:08'
    # end = '2017-12-11T17:10'
    c.execute('SELECT Grideye FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    datetime_data = c.fetchall()
    c.execute('SELECT Temperature FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    temp_data = c.fetchall()
    c.execute('SELECT Humidity FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    humidity_data = c.fetchall()
else:
    end = input("Ending date/time (Format: YYYY-MM-DDTHH:mm:ss): ")
    c.execute('SELECT Grideye FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    datetime_data = c.fetchall()
    c.execute('SELECT Temperature FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    temp_data = c.fetchall()
    c.execute('SELECT Humidity FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    humidity_data = c.fetchall()

# convert string from sql database to list
for idx, x in enumerate(grideye_data):
    grideye_data[idx] = [float(i) for i in x[0].split(',') if i != '0']
gridata = np.array(grideye_data).reshape((len(grideye_data), 8, 8))

for idx, x in enumerate(datetime_data):
    datetime_data[idx] = x[0]

for idx, x in enumerate(temp_data):
    temp_data[idx] = x[0]

for idx, x in enumerate(humidity_data):
    humidity_data[idx] = x[0]

# retrieve the thermal background for the selected node
c.execute('SELECT Background FROM background WHERE Node is {}'.format(node))
background = c.fetchall()
background = [float(i) for i in background[0][0].split(',')]

# retrieve the sum of the squared differences to calculate the std dev of the background
c.execute('SELECT SumSqDif FROM background WHERE Node is {}'.format(node))
sum_sq_dif = c.fetchall()
sum_sq_dif = [float(i) for i in sum_sq_dif[0][0].split(',')]

# retrieve the number of samples used in calculation of the sum of squared differences so far
c.execute('SELECT Sample FROM background WHERE Node is {}'.format(node))
s = c.fetchall()
s = s[0][0]

# calculate the std dev of each pixel
std_dev = []
# from sum_sq_dif, std_dev = sqrt(sum_sq_dif/s-1)
for i in sum_sq_dif:
    std_dev.append(np.sqrt(i/(s-1)))

# calculate the threshold for each pixel based on the thermal background and the std dev
threshold = []
for i in range(len(background)):
    threshold.append(background[i] + (5 * std_dev[i]))
threshold = np.array(threshold).reshape((8, 8))

iso = []
iso_all = []
blobs = []


def ema(values):
    # Numpy implementation of exponential average
    weights = np.exp(np.linspace(0., -1., len(values)))
    weights /= weights.sum()
    value = np.convolve(values, weights, mode='valid')
    return float(value)


# this class is created for each found blob and stores various data values about each blob
# it contains the functions of track movement over time
class Region:
    def __init__(self, region, datetime):
        self.start_time = [datetime]
        self.end_time = datetime
        self.readings = 1
        self.data = [region[3:]]
        self.size = region[0]
        self.max_s = self.size
        self.min_s = self.size
        self.avg_s = self.size
        self.prev_size = 0
        self.center = [region[1]]
        self.avg_temp = region[2]
        self.prev_temp = self.avg_temp
        self.active = True
        self.movement = []
        self.match = False
        self.displacement = 0
        self.duration = 0
        self.x_dis = 0
        self.y_dis = 0
        self.bearing = [0.]
        self.velocity = [0.]
        self.prediction = [region[1]]
        # self.prediction = [[0, 0]]

    # checks distance between two regions:
    # pick 0 to find the euclidean distance
    # pick 1 to find the separate x and y displacement
    # pick 2 to find the euclidean distance between the new hotspot and the regions latest prediction

    def check_distance(self, choice, region2):
        if self.active:
            if choice == 0:
                # return math.sqrt((self.center[-1][0] - region2[1][0])**2 + (self.center[-1][1] - region2[1][1])**2)
                return math.sqrt((region2[1][0] - self.center[-1][0]) ** 2 + (region2[1][1] - self.center[-1][1]) ** 2)

            elif choice == 1:
                # return region2[1][0] - self.center[-1][0], self.center[-1][1] - region2[1][1]
                return region2[1][0] - self.center[-1][0], region2[1][1] - self.center[-1][1]

            elif choice == 2:
                return math.sqrt((region2[1][0] - self.prediction[-1][0])**2
                                 + (region2[1][1] - self.prediction[-1][1])**2)
        else:
            return 16

    def predict_movement(self):
        pred = [0, 0]
        pred[0] = self.center[-1][0] + ema(self.velocity) / 2 * np.cos(self.bearing[-1] * np.pi / 180)
        pred[1] = self.center[-1][1] + ema(self.velocity) / 2 * np.sin(self.bearing[-1] * np.pi / 180)
        # pred[0] = self.center[-1][0] + self.velocity[-1] * np.cos(self.bearing[-1] * np.pi / 180)
        # pred[1] = self.center[-1][1] + self.velocity[-1] * np.sin(self.bearing[-1] * np.pi / 180)
        # pred = list(np.clip(pred, 0, 7))
        self.prediction.append(pred)

    def check_movement(self, region2, datetime2):
        # if -5 < self.center[-1][0] - region2[1][0] < 5 and -5 < self.center[-1][1] - region2[1][1] < 5 \
        if self.check_distance(2, region2) < 5 and self.active and not self.match:
            self.start_time.append(datetime2)
            self.end_time = datetime2
            self.duration = (dt.datetime.strptime(a.end_time, "%Y-%m-%dT%H:%M:%S:%f") -
                             dt.datetime.strptime(a.start_time[0], "%Y-%m-%dT%H:%M:%S:%f")).total_seconds()
            self.data.append(region2[3:])
            self.readings += 1
            self.prev_size = self.size
            self.size = region2[0]
            if self.size > self.max_s:
                self.max_s = self.size
            if self.size < self.min_s:
                self.min_s = self.size
            self.avg_s = (self.avg_s * (self.readings - 1) + region2[0]) / self.readings
            self.displacement += self.check_distance(0, region2)
            self.velocity.append(self.displacement / self.duration)
            self.x_dis, self.y_dis = map(add, [self.x_dis, self.y_dis], self.check_distance(1, region2))
            self.bearing.append(np.arctan2(self.y_dis, self.x_dis)*(180/np.pi))
            self.center.append(region2[1])
            self.prev_temp = self.avg_temp
            # self.avg_temp = np.mean([x[2] for x in self.data[-1]])
            self.avg_temp = (self.prev_temp * (self.readings - 1) + region2[2]) / self.readings
            self.movement.append(True)
            self.match = True
            return True
        elif self.match:
            return False
        else:
            # self.active = False
            self.movement.append(False)
            return False


def floodfill(matrix, rows, columns):
    # I will use a queue to keep record of the positions we are gonna traverse.
    # Each element in the queue is a coordinate position (row,column) of an element
    # of the matrix.

    # Returns region into reg variable with the following structure
    # region = [size(n),[center x, center y], avg temp C, [ro,co,data]_1, [ro,co,data]_2, ..., [ro,co,data]_n]

    matrix = copy(matrix)
    q = Queue()
    # --
    region = [0, [0, 0], 0]

    # A container for the up, down, left, right, and diagonal directions.
    # dirs = {(-1, 0), (1, 0), (0, -1), (0, 1)}
    dirs = {(-1, 1), (0, 1), (1, 1), (-1, 0), (1, 0), (-1, -1), (0, -1), (1, -1)}

    # Now we will add our initial position to the queue.
    q.put((rows, columns, matrix[rows][columns]))

    # And we will mark the element as null. You will definitely need to
    # use a boolean matrix to mark visited elements. In this case I will simply
    # mark them as null.
    matrix[rows][columns] = 0

    # Go through each element in the queue, while there are still elements to visit.
    while not q.empty():

        # Get the next element to visit from the queue.
        # Remember this is a (row, column) position.
        # a = q.get()

        ro, co, data = q.get()

        # Add the element to the output region.
        region.append([ro, co, data])
        # --
        region[0] += 1

        # Check for non-visited position adjacent to this (ro,co) position.
        # includes up, down, left, right, and diagonals
        for (dr, dc) in dirs:

            # Check if this adjacent position is not null and keep it between
            # the matrix size.
            if 0 <= (ro + dr) < matrix.shape[0] and 0 <= (co + dc) < matrix.shape[1]:
                if matrix[ro + dr][co + dc] > threshold[ro + dr][co + dc]:
                    # Then add the position to the queue to be visited later
                    q.put((ro + dr, co + dc, matrix[ro + dr][co + dc]))
                    # And mark this position as visited.
                    matrix[ro + dr][co + dc] = 0

    # Calculate the center of the hotspot weighted to the temperatures
    region[1] = list(np.average([[i[0], i[1]] for i in region[3:]], axis=0, weights=[i[2] for i in region[3:]]))
    # calculate the average temp
    region[2] = np.mean([i[2] for i in region[3:]])
    # When there are no more positions to visit. You can return the
    # region visited.
    return region


# Parse through the data and check for hotspots
for i in range(len(grideye_data)):
    iso.append(datetime_data[i])
    # --
    iso.append(0)
    for row in range(8):
        for column in range(8):
            if (not any([[row, column, gridata[i][row][column]] in item[3:] for item in iso[2:]])) \
                    and gridata[i][row][column] > threshold[row][column]:
                reg = floodfill(gridata[i], row, column)
                # if reg[0] > 1:  # omits regions that are only 1 pixel large
                iso.append(reg)
                iso[1] += 1

    iso_all.append(iso)
    iso = []


# Parse through the data and check for movement between frames
for iso in iso_all:

    # if there aren't any hotspots at the current timestamp, mark all active blobs inactive
    if iso[1] == 0:
        for a in blobs:
            a.match = False
            a.active = False
        continue
    # if iso[0] == '2017-11-15T13:37:24:260580':
    #     print('break here')
    # find the distances between each blob and the hotspots at the current timestamp
    iso_dist = []
    for a in blobs:
        a.movement = [False]
        if a.active:
            iso_dist.append([a.check_distance(2, iso[i+2]) for i in range(iso[1])])

    # if there's only one active blob, assign the closest hotspot to it and create now blobs out of the others if any
    if len(iso_dist) == 1:
        min_dist_idx = iso_dist[0].index(min(iso_dist[0]))
        for i in range(iso[1]):
            if i == min_dist_idx:
                for a in blobs:
                    if a.check_movement(iso[i+2], iso[0]):
                        pass
                    elif a.active:
                        blobs.append(Region(iso[i+2], iso[0]))
                        blobs[-1].match = True
                        break
                    else:
                        pass
            else:
                blobs.append(Region(iso[i+2], iso[0]))
                blobs[-1].match = True

    # if there's multiple active blobs, assign the hotspots to the blobs closest to them, creating new blobs for any
    # left over
    elif len(iso_dist) > 1:
        iso_dist = np.array(iso_dist)
        idx, min_dist_idx = op.linear_sum_assignment(iso_dist)
        blobidx = 0
        for n, i in enumerate(idx):
            for a in blobs:
                if a.active:
                    if blobidx == i:
                        if a.check_movement(iso[min_dist_idx[n]+2], iso[0]):
                            break
                        elif a.active and not a.match:
                            blobs.append(Region(iso[min_dist_idx[i] + 2], iso[0]))
                            blobs[-1].match = True
                            break
                        else:
                            pass
                    else:
                        a.active = False
                        blobidx += 1
            blobidx += 1

        for i in [i for i in range(iso[1]) if i not in min_dist_idx]:
            blobs.append(Region(iso[i+2], iso[0]))
            blobs[-1].match = True
    else:
        for i in range(iso[1]):
            blobs.append(Region(iso[i + 2], iso[0]))
            blobs[-1].match = True
    """
        for a in blobs:
            a.movement = [False]
            if a.active and iso[1] > 1:
                iso_dist = [a.check_distance(2, iso[i+2]) for i in range(iso[1])]
                try:
                    min_dist_idx = iso_dist.index(min(iso_dist))
                except ValueError:
                    pass
                print('distance from blob: {}\n to isos at time: {}\n iso_dist: {}\n'
                       .format(a.start_time[0], iso[0], iso_dist))

        for i in range(iso[1]):
            iso_match = []
            for a in blobs:
                if a.check_movement(iso[i+2], iso[0]):
                    iso_match.append(True)
                    break
            if True not in iso_match:
                blobs.append(Region(iso[i+2], iso[0]))
                blobs[-1].match = True
    """

    # Keep a blob active it it saw activity otherwise, mark it inactive
    for a in blobs:
        a.match = False
        if True in a.movement:
            a.active = True
            a.predict_movement()
        elif False in a.movement:
            a.active = False
        else:
            continue

# This prints all of the observed events, along with various information about them.
# print('\nBLOBS\n')
# raise
numEnter = 0
numLeave = 0
timeEnter = []
timeLeave = []
angles = []

for a in blobs:
    if a.readings > 1:
        # Print the time that the object was initially measured
        # print('\nTime started: {}'.format(a.start_time[0]))

        # Print a list of the centers, bearings, velocities, and predictions
        # for i in range(a.readings):
        #     print('Time: {} - Center: {} - Bearing: {} - Velocity: {} - Prediction: {}'
        #           .format(a.start_time[i], a.center[i], a.bearing[i], a.velocity[i], a.prediction[i]))

        # Print the location in the measurement grid that the object was initially measured
        # print('Starting location: {}'.format(a.center[0]))

        # Print the displacement over the x axis and y axis
        # print('Displacement X: {} Y: {}'.format(a.x_dis, a.y_dis))

        # Print the direction of movement through the measurement grid (-180 to +180)
        # print('Bearing: {}'.format(np.arctan2(a.y_dis, a.x_dis)*(180/np.pi)))
        # print('Bearing: {}'.format(a.bearing[-1]))

        # Print the number of measurements the object was present in
        # print('# of readings: {}'.format(a.readings))

        # Print the total distance moved (not displacement) through the measurement grid
        # print('Total distance: {}'.format(a.displacement))

        # Print the amount of time that object was in the measurement grid
        # print('Total duration: {}'.format(a.duration))

        # Based on the distance moved and duration, calculate and display the velocity through the measurement grid
        # print('Velocity: {}'.format(a.velocity[-1]))

        # Print the average temperature of the object
        # print('Average temp: {}'.format(a.avg_temp))

        # Print the minimum, maximum and average sizes of the object as it was being observed in the measurement grid
        # print('Min/Max/Avg Sizes: {}/{}/{}'.format(a.min_s, a.max_s, a.avg_s))

        # Print the temporal data of each object, see how the object moves over time
        # for idx, x in enumerate(a.data):
        #     print('{}: {}: {:.2f}, {:.2f}: {}'.format(idx, a.start_time[idx], a.center[idx][0], a.center[idx][1], x))

        # Print the time that the last measurement of the object was taken
        # print('Time ended: {}'.format(a.end_time))
        print()

        times = ','.join(map(str, a.start_time))
        centers = ','.join(map(str, a.center))
        AvgBearing = np.mean(a.bearing[1:])
        bearings = ','.join(map(str, a.bearing[1:]))
        AvgVelocity = ema(a.velocity[1:])
        velocities = ','.join(map(str, a.velocity[1:]))
        predictions = ','.join(map(str, a.prediction))

# uncomment this section to store traffic entities in database
        # c.execute("REPLACE INTO blobs"
        #           " (TimeStart, TimeEnd, Times, Readings, Duration, AvgSize, AvgTemp, Displacement,"
        #           " Centroids, AvgBearing, Bearings, AvgVelocity, Velocities, Predictions)"
        #           " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        #           (a.start_time[0], a.end_time, times, a.readings, a.duration, a.avg_s, a.avg_temp, a.displacement,
        #            centers, AvgBearing, bearings, AvgVelocity, velocities, predictions))
        # conn.commit()

        if 2 < a.readings < 10:
            angles.append(AvgBearing)
            if AvgBearing > 0:
                numLeave += 1
                timeLeave.append(dt.datetime.strptime(a.start_time[0], "%Y-%m-%dT%H:%M:%S:%f"))
            if AvgBearing < 0:
                numEnter += 1
                timeEnter.append(dt.datetime.strptime(a.start_time[0], "%Y-%m-%dT%H:%M:%S:%f"))

if start != 'all':
    print('During this time period {} to {}\n  {} left the area and {} entered the area'
          .format(start, end, numLeave, numEnter))
else:
    print('{} left the area and {} entered the area'.format(numLeave, numEnter))

conn.close()

datetime_data2 = []
for i in datetime_data:
    datetime_data2.append(dt.datetime.strptime(i, "%Y-%m-%dT%H:%M:%S:%f"))
# plot a polar plot showing angles of movement through measurement area
# angles = np.array(angles)
# x = np.array([np.pi/4, 5*np.pi/4])
# gtruth = [42, 37] # 46 people leaving 38 people entering
# rads = angles * (np.pi / 180)
#
# bins_num = 8
# bins = np.linspace(-np.pi, np.pi, bins_num + 1)
# n, _, _ = plt.hist(rads, bins)
# plt.clf()
# width = 2 * np.pi / bins_num
# ax = plt.subplot(1, 1, 1, polar='True')
# bars = ax.bar(bins[:bins_num], n, width=width, bottom=0.0)
# bars2 = ax.bar(x, gtruth, width=width/2)
# for bar in bars:
#     bar.set_alpha(0.5)
# for bar in bars2:
#     bar.set_alpha(0.5)
# ax.set_xticklabels(['0°', '45°', 'Number of People Exiting Room\n90°', '135°', '180°', '225°',
#                     '270°\nNumber of People Entering Room', '315°'])
# plt.legend(['Traffic Algorithm', 'Actual'], loc='center left')
# plt.show()

# plot a timeline graph of when people are entering and leaving compared to climate info
fig, ax = plt.subplots()
ax.scatter(timeLeave, [2 for i in timeLeave], label="Person Leaving ({})".format(numLeave))
ax.scatter(timeEnter, [1 for i in timeEnter], label="Person Entering ({})".format(numEnter))
ax.legend()

ax2 = ax.twinx()
ax2.plot(datetime_data2, temp_data, 'r-')
ax2.set_ylim(25, 28)
ax2.set_ylabel('Temperature °C')
ax2.yaxis.label.set_color('red')


ax3 = ax.twinx()
ax3.yaxis.tick_left()
ax3.yaxis.set_label_position("left")
ax3.plot(datetime_data2, humidity_data, 'g-')
ax3.set_ylim(41, 49)
ax3.set_ylabel('% Relative Humidity')
ax3.yaxis.label.set_color('green')

ax.set_ylim(0, 10)

fig.autofmt_xdate()
myFmt = mdates.DateFormatter('%H:%M')
ax.xaxis.set_major_formatter(myFmt)
ax.set_xlabel('Time')

ax.yaxis.set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_visible(False)
ax.spines['top'].set_visible(False)
plt.xlim(dt.datetime.strptime(start, "%Y-%m-%dT%H:%M") - dt.timedelta(minutes=30),
         dt.datetime.strptime(end, "%Y-%m-%dT%H:%M") + dt.timedelta(minutes=30))
plt.grid()
plt.show()
