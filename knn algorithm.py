# --------------------------------------------------------------------------------------------- 
#                                                                                               
#   University of North Texas                                                                   
#   Department of Electrical Engineering                                                        
#                                                                                               
#   Faculty Advisors:   Dr. Xinrong Li, Dr. Jesse Hamner, Dr. Song Fu                                    
#   Name:               Ovie Onoriose                                                           
#                                                                                            
#   Title:              KNN algorithm                                 
#   Version:            1                                                                  
#                                                                                               
#   Description:                                                                                
#       This script takes data collected by the nodes and stored in the occupancy
# 		database and analyzes it using the KNN algorithm. It pulls training data from a table
# 		also located in the database.
#                                                                                               
#   Dependencies:                                                                               
#       Python 3.5.1, sqlite3, numpy, matplotlib 

from queue import Queue
import numpy as np
from scipy import optimize as op
from matplotlib import pyplot as plt
# from matplotlib import dates as mdates
import sqlite3
from copy import copy
import datetime as dt
import math
from operator import add

node = 1

# retreive training data for knn algorithm
conn = sqlite3.connect("occupancy.db")
c = conn.cursor()
c.execute('SELECT Pixels, Hotspots, num_people FROM training')
training = c.fetchall()


c.execute("CREATE TABLE IF NOT EXISTS KNN"
          "(Node integer, Times text, Pixels integer, Hotspots integer, num_people integer, gtruth integer) ")
while True:
    node = input("Which Node are you wanting to analyze data from? (1 or 2)")
    if node in ['1', '2']:
        node = float(node)
        break
    else:
        print("Please choose either 1 or 2")

start = input("Starting date/time (Format: YYYY-MM-DDTHH:mm:ss) (enter 'all' to take all measurements): ")
if start == 'all':
    c.execute('SELECT Grideye FROM data WHERE Node = {}'.format(node))
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data WHERE Node = {}'.format(node))
    datetime_data = c.fetchall()
elif start == 'test':
    start = '2018-09-29T19:30'
    end = '2018-09-29T20:00'
    c.execute('SELECT Grideye FROM data WHERE Node = {} AND Datetime BETWEEN "{}" AND "{}"'.format(node, start, end))
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data WHERE Node = {} AND Datetime BETWEEN "{}" AND "{}"'.format(node, start, end))
    datetime_data = c.fetchall()
else:
    end = input("Ending date/time (Format: YYYY-MM-DDTHH:mm:ss): ")
    c.execute('SELECT Grideye FROM data WHERE Node = {} AND Datetime BETWEEN "{}" AND "{}"'.format(node, start, end))
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data WHERE Node = {} AND Datetime BETWEEN "{}" AND "{}"'.format(node, start, end))
    datetime_data = c.fetchall()

# convert string from sql database to list
for idx, x in enumerate(grideye_data):
    grideye_data[idx] = [float(i) for i in x[0].split(',') if i != '0']
gridata = np.array(grideye_data).reshape((len(grideye_data), 8, 8))

for idx, x in enumerate(datetime_data):
    datetime_data[idx] = x[0]

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
    threshold.append(background[i] + (6 * std_dev[i]))
threshold = np.array(threshold).reshape((8, 8))

iso = []
iso_all = []


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
    iso.append(0)  # number of total active pixels
    iso.append(0)  # number of hotspots at this time
    for row in range(8):
        for column in range(8):
            if (not any([[row, column, gridata[i][row][column]] in item[3:] for item in iso[3:]])) \
                    and gridata[i][row][column] > threshold[row][column]:
                reg = floodfill(gridata[i], row, column)
                # if reg[0] > 1:  # omits regions that are only 1 pixel large
                iso.append(reg)
                iso[1] += reg[0]
                iso[2] += 1

    iso_all.append(iso)
    iso = []

xplots = []
yplots = []

# iso format (datetime, # of active pixels, # of hotspots, hotspots)
for data in iso_all:
    time = data[0]
    pixels = data[1]
    hotspots = data[2]
    distance = []

    for train_value in training:
        distance.append(math.sqrt((train_value[1]-hotspots)**2 + (train_value[0]-pixels)**2))
    distance = np.array(distance)
    KNNindices = np.argpartition(distance, 4)
    KNNindices = KNNindices[:4]
    guess = np.mean([training[i][2] for i in KNNindices])
    data.append(guess)
    # print("time: {} - pixels: {} - hotspots: {} - guess: {}\n".format(time, pixels, hotspots, guess))
    c.execute("REPLACE INTO KNN"
              " (Node, Times, Pixels, Hotspots, num_people) VALUES (?, ?, ?, ?, ?)", (node, time, pixels, hotspots, guess))
    conn.commit()
    xplots.append(dt.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S:%f"))
    yplots.append(guess)


plt.plot(xplots, yplots, marker='o')
plt.gcf().autofmt_xdate()
plt.show()

conn.close()
