import numpy as np
from matplotlib import pyplot as plt
import sqlite3
import datetime as dt
import math

conn = sqlite3.connect("occupancy.db")
c = conn.cursor()

while True:
    node = input("Which Node are you wanting to analyze data from? (1 or 2): ")
    if node in ['1', '2']:
        node = float(node)
        break
    else:
        print("Please choose either 1 or 2")

start = input("Starting date/time (Format: YYYY-MM-DDTHH:mm:ss) (enter 'all' to take all measurements): ")
if start == 'all':
    c.execute('SELECT Times FROM KNN WHERE Node = {}'.format(node))
    datetime_data = c.fetchall()
    c.execute('SELECT gtruth FROM KNN WHERE Node = {}'.format(node))
    gtruth = c.fetchall()
    c.execute('SELECT num_people FROM KNN WHERE Node = {}'.format(node))
    guess = c.fetchall()
    guess = [x[0] for x in guess]
elif start == 'test':
    start = '2018-09-29T19:36:58:870588'
    end = '2018-09-29T19:47:11:905538'
    c.execute('SELECT gtruth FROM KNN WHERE Node = {} AND Times BETWEEN "{}" AND "{}"'.format(node, start, end))
    gtruth = c.fetchall()
    c.execute('SELECT num_people FROM KNN WHERE Node = {} AND Times BETWEEN "{}" AND "{}"'.format(node, start, end))
    guess = c.fetchall()
    guess = [x[0] for x in guess]
    c.execute('SELECT Times FROM KNN WHERE Node = {} AND Times BETWEEN "{}" AND "{}"'.format(node, start, end))
    datetime_data = c.fetchall()
else:
    end = input("Ending date/time (Format: YYYY-MM-DDTHH:mm:ss): ")
    c.execute('SELECT num_people FROM KNN WHERE Node = {} AND Times BETWEEN "{}" AND "{}"'.format(node, start, end))
    guess = c.fetchall()
    c.execute('SELECT gtruth FROM KNN WHERE Node = {} AND Times BETWEEN "{}" AND "{}"'.format(node, start, end))
    gtruth = c.fetchall()
    guess = [x[0] for x in guess]
    c.execute('SELECT Times FROM KNN WHERE Node = {} AND Times BETWEEN "{}" AND "{}"'.format(node, start, end))
    datetime_data = c.fetchall()

# lets find RMSE for data with not rounded values
sqdifs = []

for i in range(len(guess)):
    sqdifs.append((guess[i]-gtruth[i][0])**2)

mean = sum(sqdifs)/len(sqdifs)
rmse = math.sqrt(mean)
print('Mean of SSD of non rounded values is: {}'.format(mean))
print('RMSE of non rounded values is : {}'.format(rmse))

# finding RMSE using rounded values
sqdifs = []

for i in range(len(guess)):
    sqdifs.append((np.round(guess[i])-gtruth[i][0])**2)

mean = sum(sqdifs)/len(sqdifs)
rmse = math.sqrt(mean)
print('Mean of SSD of rounded values is: {}'.format(mean))
print('RMSE of rounded values is : {}'.format(rmse))

xplots = []
yplots = []

for x in datetime_data:
    xplots.append(dt.datetime.strptime(x[0], "%Y-%m-%dT%H:%M:%S:%f"))

# format times on x axis
ticks_to_plot = xplots[1::20]
labels = [dt.datetime.strftime(i, "%H:%M:%S") for i in ticks_to_plot]

# take KNN guesses, round them to nearest int and put them in list for graphing
for i in guess:
    yplots.append(np.round(i))

# plot KNN guesses and ground truth on plot
plt.plot(xplots, yplots, marker='o')
plt.plot(xplots, gtruth, marker='o')
plt.legend(['Occupancy Algorithm', 'Actual'], loc='upper left')
plt.xlabel('Time', fontsize=15)
plt.ylabel('Number of People in Measurement Area', fontsize=15)

# format axis
ax = plt.gca()
ax.set_xticks(ticks_to_plot)
ax.set_xticklabels(labels)
ax.set_xticklabels(labels, rotation=45)

plt.show()
