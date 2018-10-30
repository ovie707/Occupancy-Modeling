# --------------------------------------------------------------------------------------------- 
#                                                                                               
#   University of North Texas                                                                   
#   Department of Electrical Engineering                                                        
#                                                                                               
#   Faculty Advisors:   Dr. Xinrong Li, Dr. Jesse Hamner, Dr. Song Fu
#   Name:               Ovie Onoriose                                                           
#                                                                                               
#   Title:              stopdata                                      
#   Version:            1                                                                  
#                                                                                               
#   Description:                                                                                
#       Use this file to stop data collection on the nodes. 
#		When you stop the script that collects data from the nodes, the node itself
#		will still be collecting and broadcasting data. Use this script to stop that collection                   
#                                                                                               
#   Dependencies:                                                                               
#       Python 3.5.1, Pyserial,                                                        

import serial
import time

# ser = serial.Serial("/dev/ttyAMA0",115200,timeout = 350) #open serial port for RPi
ser = serial.Serial("COM3",115200,timeout = 350) #open serial port for RPi

print('stop_data has started')
ser.flushInput()
ser.flushOutput()
print('stop_data has cleared serial port')
time.sleep(.1)
end_data = [0x7E, 0x00, 0x10, 0x17, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFE,
			0x02, 0x44, 0x31, 0x04, 0x72]
ser.write(end_data)
print('stop_data has sent stop request')