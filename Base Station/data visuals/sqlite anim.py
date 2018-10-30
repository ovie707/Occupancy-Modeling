
# --------------------------------------------------------------------------------------------- 
#                                                                                               
#   University of North Texas                                                                   
#   Department of Electrical Engineering                                                        
#                                                                                               
#   Faculty Advisors:   Dr. Xinrong Li, Dr. Jesse Hamner, Dr. Song Fu
#   Name:               Ovie Onoriose                                                           
#                                                                                                                                                                                              
#   Title:              Grideye Animator for data from SQlite database
#   Version:            1.2                                                             
#                                                                                               
#   Description:                                                                                
#       This script retrieves grideye data from a local sqlite database and creates
#       an animation from that data. The user can specify the dates that they would
#       like to gather data between as well as the frame rate of the produced animation                 
#                                                                                               
#   Dependencies:                                                                               
#       Python3.5.1, Numpy, Matplotlib, sqlite3, ffmpeg
#
#   Change Log:
#        02/02/2017
#        Script now asks user for starting and ending datetimes on startup. Added some
#        code to remove a future warning that would arise. (numpy.full would raise warning
#        if dtype wasn't specified.
#
#        11/08/2017
#        rotated video to be consistant with caluclations from algorithm
#        basically converted rows and columns array indices to x and y coordinates

import numpy as np
from matplotlib import pyplot as plt
import sqlite3


fps = 5

# connect to database and fetch data
datab = input("Make video from traffic database or KNN database? \n 1: traffic\n2: KNN\n")
if datab = 1:
	conn = sqlite3.connect("occupancy.db")
elif datab = 2:
		conn = sqlite3.connect("train_occupancy.db")

c = conn.cursor()

# start = input("Starting date/time (Format: YYYY-MM-DDTHH:mm:ss) (enter 'all' to take all measurements: ")
# if start != 'all':
#     end = input("Ending date/time (Format: YYYY-MM-DDTHH:mm:ss): ")

file_name = input("Enter a file name: ") or "animation"


start = input("Starting date/time (Format: YYYY-MM-DDTHH:mm:ss) (enter 'all' to take all measurements): ")
if start == 'all':
    c.execute('SELECT Grideye FROM data')
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data')
    datetime_data = c.fetchall()
# elif start == 'test':
#     start = '2017-10-06T05:47:09:231006'
#     end = '2017-10-06T05:48:28:725764'
#     c.execute('SELECT Grideye FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
#     grideye_data = c.fetchall()
#     c.execute('SELECT Datetime FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
#     datetime_data = c.fetchall()
else:
    end = input("Ending date/time (Format: YYYY-MM-DDTHH:mm:ss): ")
    c.execute('SELECT Grideye FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    grideye_data = c.fetchall()
    c.execute('SELECT Datetime FROM data WHERE Datetime BETWEEN "{}" AND "{}"'.format(start, end))
    datetime_data = c.fetchall()

# convert string from sql database to list
for idx, x in enumerate(grideye_data):
    grideye_data[idx] = [float(i) for i in x[0].split(',') if i != '0']

for idx, x in enumerate(datetime_data):
    datetime_data[idx] = x[0]

# for idx, x in enumerate(new_regions):
#     new_regions[idx] = x[0]

gridata = np.array(grideye_data).reshape((len(grideye_data), 8, 8))
for idx, i in enumerate(gridata):
    gridata[idx] = np.rot90(gridata[idx])
    grideye_data[idx] = gridata[idx].flatten()


# Set up the figure
fig = plt.figure()
ax = fig.add_subplot(111)
ax.set_yticklabels([])
ax.set_xticklabels([])
a = np.full((8, 8), 20, dtype=int)
im = ax.imshow(a, vmin=20, vmax=30, interpolation='none', cmap=plt.get_cmap('hot'))
ttl = ax.text(.01, 1.005, '', transform=ax.transAxes)
num = []
for (i, j), z in np.ndenumerate(np.full((8, 8), 20, dtype=int)):
    num.append(ax.text(j, i, '{:0.1f}'.format(z), ha='center', va='center'))


# Set up initial frame of animation
def init():
    im.set_data(np.full((8,8),20,dtype=int))
    ttl.set_text('')
    for i in range(len(num)):
        num[i].set_text('')
    return [im, ttl, num]


# Set up frames afterwards
def animate(i):
    im.set_data(gridata[i])
    # if datetime_data[i] in new_regions:
    #     ttl.set_text('Frame: {}   New Region!\nTime: {}'.format(i, datetime_data[i]))
    # else:
    ttl.set_text('Frame: {}\nTime: {}'.format(i, datetime_data[i]))
    for n in range(len(num)):
        num[n].set_text('{:0.1f}'.format(grideye_data[i][n]))
    return [im, ttl, num]


plt.rcParams['animation.ffmpeg_path'] = 'c:\\ffmpeg\\bin\\ffmpeg.exe'
from matplotlib import animation  # for some reason a warning is thrown if this is declared before plt.rcParams
anim = animation.FuncAnimation(fig, animate, init_func=init, frames=len(gridata), blit=False)
anim.save('{}.mp4'.format(file_name), fps=fps)
# plt.show(block=False)
print('animation saved\n')

