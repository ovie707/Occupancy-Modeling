import numpy as np
import matplotlib.pyplot as plt
import sqlite3

# conn = sqlite3.connect('D:\Google Drive\School\Thesis\Codes\Raspberry Pi\current\grideye revA\occupancy.db')
# conn = sqlite3.connect("C:\\Users\\ovie7\\Google Drive\\School\\Thesis\\Codes\\Raspberry Pi\\current\\grideye revA\\occupancy.db")
conn = sqlite3.connect("occupancy.db")
c = conn.cursor()

start = input("Starting date/time (Format: YYYY-MM-DDTHH:mm:ss) (enter 'all' to take all measurements): ")
if start == 'all':
    c.execute('SELECT AvgBearing FROM blobs')
    angles = c.fetchall()
elif start == 'test':
    start = '2017-11-15T11:30'
    end = '2017-11-15T18:30'
    c.execute('SELECT AvgBearing FROM blobs WHERE TimeStart BETWEEN "{}" AND "{}" AND Readings BETWEEN 2 AND 10'.format(start, end))
    angles = c.fetchall()
else:
    end = input("Ending date/time (Format: YYYY-MM-DDTHH:mm:ss): ")
    c.execute('SELECT AvgBearing FROM blobs WHERE TimeStart BETWEEN "{}" AND "{}" AND Readings BETWEEN 2 AND 10'
              .format(start, end))
    angles = c.fetchall()

angles = [i[0] for i in angles]

angles = np.array(angles)
x = np.array([np.pi/2, -np.pi/2])
gtruth = [46, 38]  # 46 people leaving 38 people entering
rads = angles * (np.pi / 180)

bins_num = 8
bins = np.linspace(-np.pi, np.pi, bins_num + 1)
n, _, _ = plt.hist(rads, bins)
plt.clf()
width = 2 * np.pi / bins_num
ax = plt.subplot(1, 1, 1, polar='True')
bars = ax.bar(bins[:bins_num], n, width=width, bottom=0.0)
bars2 = ax.bar(x, gtruth, width=width/2)
for bar in bars:
    bar.set_alpha(0.75)
for bar in bars2:
    bar.set_alpha(0.25)
ax.set_xticklabels(['0°', '45°', 'Number of People Exiting Room\n90°', '135°', '180°', '225°',
                    '270°\nNumber of People Entering Room', '315°'])
plt.legend(['Traffic Algorithm', 'Actual'], loc='center left')
plt.show()
