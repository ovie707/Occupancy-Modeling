/*
 * Ovie Onoriose

OccupancyV1.5.1

Receives a request from xbee coordinator using a pin interrupt
Gathers data from sensors and creates packet to send back
Sends packet back to Xbee coordinator, making use of Xbee API mode

Sensors:
Panasonic Grid-Eye
Adafruit PIR
RHT03 temp/humidty sensor

Wireless:
Xbee Pro S2B

Changelog
10/24/2016:
added variable for node identifier

11/21/2016
added support for PIR sensor (init_PIR)

02/19/2017
only requested data from grideye when pir was triggered (should save power)

03/03/2017
revised PIR trigger method. A timer now counts down once the PIR is inactive. Once it reaches
zero, the grideye isn't called for data. When the PIR is active, the timer resets.

03/21/2017
revised PIR trigger method. LED denotes PIR state.
Green = PIR is active (grideye is polled)
Blue = PIR is inactive but inactivity timer hasn't reached 0 (grideye is still being polled)
Red = PIR is inactive and inactivity timer has reached 0 (grideye isn't polled -> 1 degree temps in database)


07/19/2017
LED now flashes instead of staying solid
added functionality to push button to enable and disable measurement transmission, just in case the xbee pin interrupt isn't read.
rearranged somethings to make code more clear

07/23/2017
Computing a threshold value for the algorithm dynamically based on a std dev of the grideye temperature values

08/08/2017
Offloading dynamic threshold computation to central database for simplicity

*/

//includes
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "stdarg.h"
#include "inc/hw_memmap.h"
#include "inc/hw_types.h"
#include "inc/hw_ints.h"
#include "driverlib/sysctl.h"
#include "driverlib/interrupt.h"
#include "driverlib/gpio.h"
#include "driverlib/timer.h"
#include "driverlib/pin_map.h"
#include "driverlib/uart.h"
#include "driverlib/i2c.h"
#include "utils/uartstdio.h"

//function prototypes
void init_func(void); //consolidate all inits into one
void init_UART(int choice); // enables uart
void Xbee_trigger_en(void);
void SW1_trigger_en(void);
void trigger(void);
void grideye(void); // reads sensor data from grideye
void rht03(void); //reads temperature and humidty from the RHT03
void pir(void); //reads the PIR
void send_data_packet(char *data); // sends data out the uart in API transmit request format to go to Rpi
void inactive_bg(void); //updates the background when there has been no activity
void active_bg(void); //updates the background when there has been activity
void setOpMode(int mode); //sets the operation mode of the grideye
void setFrameRate(int frame_rate); // sets the frame rate of the grideye 1 for 1fps 0 for 10fps
int thermistor(void); // reads the temperature of the grideye
void init_I2C(void); //initializes I2C with the grideye
void sendI2C(int slave_addr, int data_amount, ...); //function to send values over i2c
int getI2C(int slave_addr, int reg); //function to read registers over I2C

//variables
char duty = 0, grideye_data[128] = {0}, rht03_data[5] = {0}, node = 1, pir_timer = 10, pir_data = 0, location[5] = {66,66,66,66,66};
float minimum = 0., grideye_temp[64] = {0.}, background[64] = {0.}, bg_scale = 0., scaled_bg[64]={0.};
int sys_clock, m, i, j, k, sum, bg_timer = 0, pir_inactive = 0;
volatile uint32_t ui32Loop;
#define SLAVE_ADDRESS 0x68
#define TIMER_FREQ 2
#define BG_INTERVAL 15
#define UART_BAUDRATE 115200
#define XBEE 1
#define PUTTY 0
#define PACKET_SIZE 155


int main(void)
{
	// Run the clock at 40Mhz
	SysCtlClockSet(SYSCTL_SYSDIV_5|SYSCTL_USE_PLL|SYSCTL_XTAL_16MHZ|SYSCTL_OSC_MAIN);
	sys_clock = SysCtlClockGet();

	IntMasterEnable();

	//delay on startup so XBEE doesn't immediately trigger interrupt unintenionally
	//for(ui32Loop = 0; ui32Loop < 1000000; ui32Loop++){}

	init_I2C();
	setOpMode(0x00); 	//setting the operation mode of the grideye to normal
	setFrameRate(0); 	//setup the grideye to refresh the registers at 10fps
	init_func();		//Setup the PIR, Xbee digital input, and timers
	init_UART(XBEE); 	//set to 1 for xBee output //set to 0 for Putty output

	while(1){}
}

void init_func(void)
{
	//PIR initialization
	//PE3 for PIR
	SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOE);
	while(!SysCtlPeripheralReady(SYSCTL_PERIPH_GPIOE)){}
	GPIOPinTypeGPIOInput(GPIO_PORTE_BASE, GPIO_PIN_3);
	GPIOPadConfigSet(GPIO_PORTE_BASE, GPIO_PIN_3, GPIO_STRENGTH_2MA, GPIO_PIN_TYPE_STD_WPD);
	//LED initializaiton
	SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOF);
	while(!SysCtlPeripheralReady(SYSCTL_PERIPH_GPIOF)){}
	GPIOPinTypeGPIOOutput(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3);
	GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 0);

	//Digital pin initialization for interrupt from Xbee on PE1
	GPIOPinTypeGPIOInput(GPIO_PORTE_BASE, GPIO_PIN_1);
	GPIOPadConfigSet(GPIO_PORTE_BASE, GPIO_PIN_1, GPIO_STRENGTH_2MA, GPIO_PIN_TYPE_STD_WPD);
	GPIOIntDisable(GPIO_PORTE_BASE, GPIO_PIN_1);
	GPIOIntClear(GPIO_PORTE_BASE, GPIO_PIN_1);
	GPIOIntRegister(GPIO_PORTE_BASE, Xbee_trigger_en);
	GPIOIntTypeSet(GPIO_PORTE_BASE, GPIO_PIN_1, GPIO_BOTH_EDGES);
	GPIOIntEnable(GPIO_PORTE_BASE, GPIO_PIN_1);
	//Switch initialization to manually control data measurement transmission
	GPIOPinTypeGPIOInput(GPIO_PORTF_BASE, GPIO_PIN_4);
	GPIOPadConfigSet(GPIO_PORTF_BASE, GPIO_PIN_4, GPIO_STRENGTH_2MA, GPIO_PIN_TYPE_STD_WPU);
	GPIOIntDisable(GPIO_PORTF_BASE, GPIO_PIN_4);
	GPIOIntClear(GPIO_PORTF_BASE, GPIO_PIN_4);
	GPIOIntRegister(GPIO_PORTF_BASE, SW1_trigger_en);
	GPIOIntTypeSet(GPIO_PORTF_BASE, GPIO_PIN_4, GPIO_FALLING_EDGE);
	GPIOIntEnable(GPIO_PORTF_BASE, GPIO_PIN_4);

	//Timer initialization that controls the measurement transmission
	// Enable and configure Timer1 peripheral.
	SysCtlPeripheralEnable(SYSCTL_PERIPH_TIMER1);
	// Configure as a 32-bit timer in periodic mode.
	TimerConfigure(TIMER1_BASE, TIMER_CFG_PERIODIC);
	// Initialize timer load register.
	TimerLoadSet(TIMER1_BASE, TIMER_A, sys_clock/TIMER_FREQ -1);
	// Registers a function to be called when the interrupt occurs.
	IntRegister(INT_TIMER1A, trigger);
	// The specified interrupt is enabled in the interrupt controller.
	IntEnable(INT_TIMER1A);
	// Enable the indicated timer interrupt source.
	TimerIntEnable(TIMER1_BASE, TIMER_TIMA_TIMEOUT);
	TimerDisable(TIMER1_BASE, TIMER_A);


}

void init_UART(int choice)
{
	if (choice == 1)
	{
		//UART outputs using the following pins
		//PB0 is Launchpad input
		//PB1 is Launchpad output
		SysCtlPeripheralEnable(SYSCTL_PERIPH_UART1);
		SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOB);
		GPIOPinConfigure(GPIO_PB0_U1RX);
		GPIOPinConfigure(GPIO_PB1_U1TX);
		GPIOPinTypeUART(GPIO_PORTB_BASE, GPIO_PIN_0 | GPIO_PIN_1);
		UARTStdioConfig(1, UART_BAUDRATE, sys_clock);
	}
	else
	{
		// UART outputs over USB to Putty
		SysCtlPeripheralEnable(SYSCTL_PERIPH_UART0);
		SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOA);
		GPIOPinConfigure(GPIO_PA0_U0RX);
		GPIOPinConfigure(GPIO_PA1_U0TX);
		GPIOPinTypeUART(GPIO_PORTA_BASE, (GPIO_PIN_0 | GPIO_PIN_1));
		UARTStdioConfig(0, UART_BAUDRATE, sys_clock);
	}
}


//Starts or stops transmissions based on Xbee digital input interrupt
void Xbee_trigger_en(void)
{
	GPIOIntClear(GPIO_PORTE_BASE, GPIO_PIN_1);

		if(GPIOPinRead(GPIO_PORTE_BASE, GPIO_INT_PIN_1))
		{
			TimerEnable(TIMER1_BASE, TIMER_A);
		}
		else
		{
			TimerDisable(TIMER1_BASE, TIMER_A);
			bg_timer = 0; //reset the 15 minute background update timer
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 0);
		}
}

//Starts or stops transmissions based on the on board button (SW1)
void SW1_trigger_en(void)
{
	if(GPIOIntStatus(GPIO_PORTF_BASE, false) & GPIO_PIN_4)
	{
		GPIOIntClear(GPIO_PORTF_BASE, GPIO_PIN_4);
		if(HWREG(TIMER1_BASE + 0x00C) == 0x01)
		{
			TimerDisable(TIMER1_BASE, TIMER_A);
			bg_timer = 0; //reset the 15 minute background update timer
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 0);
		}
		else
		{
			TimerEnable(TIMER1_BASE, TIMER_A);
		}
	}
}


//Collects a measurement to be transmitted
//Only takes a measurement if the PIR is active (someone is present)
//Updates background and/or std dev of pixels periodically
void trigger(void)
{
	TimerIntClear(TIMER1_BASE, TIMER_TIMA_TIMEOUT);
	pir();
	bg_timer += 1; //increment the 15 minute background update timer

	//update the background information
	//if(pir_inactive >= (BG_INTERVAL*60*TIMER_FREQ-1)) //if there's been no activity for 15 minutes
	if(pir_inactive >= 15)
	{
		//BACKGROUND UPDATE AND STD_DEV UPDATE HERE//
		inactive_bg();
		bg_timer = 0; //reset the bacground update timer
		pir_inactive = 0; //reset the PIR inactivity timer
	}
	//else if(bg_timer >= (BG_INTERVAL*60*TIMER_FREQ)) //once the timer has reached 15 minutes
	else if(bg_timer >= 15)
	{
		//BACKGROUND UPDATE USING THE 5 PIXELS WITH THE LOWEST TEMPERATURES HERE//
		active_bg();
		bg_timer = 0; //reset the bacground update timer
		pir_inactive = 0; //reset the PIR inactivity timer
	}

	//take a measurement of grideye
	if(pir_timer > 0) //If there is activity
	{
		grideye(); //...collect grideye data

		//get temp and humidity data
		for(i = 0; i < 5; i++)
		{
			rht03_data[i] = 0;
		}
		rht03();

		//send grideye packet.
		send_data_packet(grideye_data);
	}

}

//Reads the pir and toggles the LED in colors depending on whether it's triggered
void pir(void)
{
//	TimerIntClear(TIMER1_BASE, TIMER_TIMA_TIMEOUT);

	if(GPIOPinRead(GPIO_PORTE_BASE, GPIO_PIN_3)) //If the PIR is active...
		{
		pir_inactive = 0; //...reset the PIR inactivity timer
		pir_timer = 10; //...reset the PIR delay timer
		pir_data = 1;
		//...toggle the blue LED
		if(GPIOPinRead(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3))
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 0);
		else
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 4);
		}
	else if(pir_timer > 0) //If the PIR is inactive, but the timer hasn't reached 0...
		{
		pir_inactive += 1; //...PIR is inactive so increment the inactivity timer
		pir_timer -= 1; //...decrement the PIR delay timer
		pir_data = 0;
		//...toggle the green LED
		if(GPIOPinRead(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3))
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 0);
		else
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 8);
		}
	else //If the PIR is inactive and the timer has reached 0...
		{
		pir_inactive += 1; //...increment the inactivity timer
		pir_data = 0;
		//...toggle the red LED
		if(GPIOPinRead(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3))
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 0);
		else
			GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, 2);
		}
}

void grideye(void)
{
	for(i = 0; i < 127; i++)
	{
		grideye_data[i] = 0;
	}
	//Get grideye data
	for(i=0; i < 64; i++)
	{
		grideye_data[2*i] = getI2C(SLAVE_ADDRESS, (129+(2*i))); //temperature high register
		grideye_data[(2*i)+1] = getI2C(SLAVE_ADDRESS, (128+(2*i))); //temperature low register
	}
}

void rht03(void)
{
	int laststate = 1, counter = 0, i = 0, j = 0;

	//Delay counts for a 40Mhz clock
	int delay_1us = 13;
	int delay_30us = 800;
	int delay_5ms = 66667;

	//Enable and set PE4 as digital output
	SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOE);
	GPIOPinTypeGPIOOutput(GPIO_PORTE_BASE, GPIO_PIN_4);

	//pulls PE4 Low for 5ms
	GPIOPinWrite(GPIO_PORTE_BASE, GPIO_PIN_4, 0);
	SysCtlDelay(delay_5ms);

	//pulls PE4 High for 30us
	GPIOPinWrite(GPIO_PORTE_BASE, GPIO_PIN_4, 1);
	SysCtlDelay(delay_30us);

	//set PE4 as an digital input
	GPIOPinTypeGPIOInput(GPIO_PORTE_BASE, GPIO_PIN_4);

	//detect changes in received stream
	for(i = 0; i < 85; i++)
	{
		counter = 0;
		laststate = GPIOPinRead(GPIO_PORTE_BASE, GPIO_PIN_4);

		while (GPIOPinRead(GPIO_PORTE_BASE, GPIO_PIN_4) == laststate)
		{
			counter++;
			SysCtlDelay(delay_1us);
			if ( counter == 255 )
			{
				break;
			}
		}
		laststate = GPIOPinRead(GPIO_PORTE_BASE, GPIO_PIN_4);

		if (counter == 255)
		break;

		// ignore first 3 transitions
		if ( (i >= 4) && (i % 2 == 0) )
		{
			// shove each bit into the storage bytes
			rht03_data[j / 8] <<= 1;
			if (counter > 25) //if counter gets higher than 25, the bit is 1, if not, it's 0
				rht03_data[j / 8] |= 1;
			j++;
		}
	}

	//check to see if bits were read correctly, if they weren't, set an error flag by setting both temp and humidity to 0xFFFF.
	if (!((j > 39) && (rht03_data[4] == ((rht03_data[0] + rht03_data[1] + rht03_data[2] + rht03_data[3]) & 0xFF))))
	{
		for(i = 0; i < 4; i++)
			{
				rht03_data[i] = 0xFF;
			}
		rht03_data[4] = 0xFC;
	}
}

void send_data_packet(char *data) //data should be 128 bytes long
{
	//  data comes in as 128 byte char array (each temp register has a high and a low)
	//	Use code below to parse on receiving end to get full temp value
	//	temp[i] = high byte[i]
	//	temp << 8;    /* redundant on first loop */
	//	temp[i] += low byte[i];

	//	packet needs to contain:
	//	xbee frame stuff 17 bytes
		//start delimiter
		//two bytes for length
		//frame type (0x10 for zigbee transmit request)
		//frame id (set to 0x00 for no ack and 0x01 for ack)
		//8 bytes for desitnation address (all 0s for coordinator FFFF for broadcast)
		//2 bytes for network dest address (set to 0xFF 0xFE and use normal dest address)
		//broadcast radius (0x00)
		//options (0x00)
	/////////actual RF data//////////
	//	unit identifier 1 byte [17]
	//	CO2 data 1 byte [18]
	//  RHT03 data 4 bytes [19-22]
	//	PIR data 1 byte [23]
	//	data 128 bytes for grid eye [24 - 151]
	//	terminator 2 bytes (0xDF, 0xDF or 223,223) [152 - 153]
	//////end of actual Rf data//////
	//	xbee frame checksum 1 byte (from byte after length to byte before checksum) [154]

	//initalizing array to beginning of xbee frame (doesn't include RF data or chksum) length = PACKET_SIZE - 4
	char packet[PACKET_SIZE] = {0x7E, 0x00, 0x97, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFE, 0x00, 0x00};
	sum = 0;

	//appending RF data into packet (TOTAL 137 bytes)
	packet[17] = node; //unit identifier: this unit is #1
	packet[18] = duty; //co2 duty cycle
	for(i = 0; i < 4; i++) //temp and humidity data
	{
		packet[19+i] = rht03_data[i];
	}
	packet[23] = pir_data; //PIR data
	for(i = 0; i < 128; i++) //grideye data
	{
		packet[24 + i] = *data;
		data++;
	}

	//RF data terminators for parsing on receiving end
	packet[152] = 0xDF;
	packet[153] = 0xDF;

	//	calculating check sum
	for(i = 3; i < PACKET_SIZE - 1; i++)
	{
		sum += packet[i];
	}
	packet[154] = (0xFF - (sum & 0xFF));

	//send out that data!
	for(i = 0; i < PACKET_SIZE; i++)
	{
		UARTCharPut(UART1_BASE,packet[i]);
	}

}

void inactive_bg(void)
{
	sum = 0;
	grideye();
	//send background to Xbee for transmission
	char iabg_packet[149] = {0x7E, 0x00, 0x91, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFE, 0x00, 0x00};

	iabg_packet[17] = 0xDF;	//so that receiving end knows this is a inactive background update transmission
	iabg_packet[18] = node;
	iabg_packet[19] = 0x00; //specifies inactive background packet

	for(i = 0; i < 128; i++) //grideye data
		iabg_packet[20 + i] = grideye_data[i];

	for(i=3; i < 148; i++)
		sum += iabg_packet[i];

	iabg_packet[148] = (0xFF - (sum & 0xFF));

	//send out that data!
	for(i = 0; i < PACKET_SIZE; i++)
	{
		UARTCharPut(UART1_BASE,iabg_packet[i]);
	}
}

void active_bg(void) //afdkluhawerfjkhadjhfakljflakjhfkjafklahskfjalsjfakfck
{
	sum = 0;
	grideye();
	//send background to Xbee for transmission
	char abg_packet[149] = {0x7E, 0x00, 0x91, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xFE, 0x00, 0x00};

	abg_packet[17] = 0xEF; //so that receiving end knows this is an active background update transmission
	abg_packet[18] = node;
	abg_packet[19] = 0x01; //specifies active background packet

	for(i = 0; i < 128; i++) //grideye data
		abg_packet[20 + i] = grideye_data[i];

	for(i=3; i < 148; i++)
		sum += abg_packet[i];

	abg_packet[148] = (0xFF - (sum & 0xFF));

	//send out that data!
	for(i = 0; i < PACKET_SIZE; i++)
	{
		UARTCharPut(UART1_BASE,abg_packet[i]);
	}
}

void setOpMode(int mode)
{
	//Set the operation mode based on arguement
	//0x00 Normal mode
	//0x10 Sleep mode
	//0x20 Stand-by mode (60sec intermittence)
	//0x21 Stand-by mode (10sec intermittence)
	//Note! Once you're in sleep mode you have to return to normal mode before you can do anything else
	sendI2C(SLAVE_ADDRESS, 2, 0x00, mode);
}

void setFrameRate(int frame_rate)
{
	//Set the frame rate based on arguement
	//1: 1 FPS
	//0: 10 FPS
	sendI2C(SLAVE_ADDRESS, 2, 0x02, frame_rate);
}

int thermistor(void)
{
	int read;
	//Get the temperature of the thermistor
	read = getI2C(SLAVE_ADDRESS,0x0F);
	read <<= 8;
	read |= getI2C(SLAVE_ADDRESS,0x0E);
	//converts the value in the register to it's corresponding temperature
	return read / 16;
}

void init_I2C(void)
{

	//enable the I2C module 0
	SysCtlPeripheralEnable(SYSCTL_PERIPH_I2C0);
	while(!(SysCtlPeripheralReady(SYSCTL_PERIPH_I2C0)));

	//reset module
	SysCtlPeripheralReset(SYSCTL_PERIPH_I2C0);

	//enable GPIO peripheral that contains I2C 0
	SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOB);

	// Configure the pin muxing for I2C0 functions on port B2 and B3.
	GPIOPinConfigure(GPIO_PB2_I2C0SCL);
	GPIOPinConfigure(GPIO_PB3_I2C0SDA);

	// Select the I2C function for these pins.
	// SDA = PB3
	// SCL = PB2
	GPIOPinTypeI2CSCL(GPIO_PORTB_BASE, GPIO_PIN_2);
	GPIOPinTypeI2C(GPIO_PORTB_BASE, GPIO_PIN_3);

	//Enable and initialize the I2C0 master module
	I2CMasterInitExpClk(I2C0_BASE, sys_clock, false);

}

// function to transmit on i2c, first argument after data_amount is the register, then after that the value.
// you can only write to one register with each function call.
void sendI2C (int slave_addr, int data_amount, ...)
{
	int i;

	// Tell the master module what address it will place on the bus when communicating with the slave.
	// falce = write; true = read
	I2CMasterSlaveAddrSet(I2C0_BASE, slave_addr, false);

	//Creates a list of variables
	va_list vdata;

	//initialize the va_list with data_amount, then it'll start reading values from
	//function arguements.
	va_start(vdata, data_amount);

	//put data to be sent into FIFO
	I2CMasterDataPut(I2C0_BASE, va_arg(vdata, int));

	//if there is only one argument, use the single send I2C function
	if(data_amount == 2)
	{
		//Initiate send of data from the MCU
		I2CMasterControl(I2C0_BASE, I2C_MASTER_CMD_SINGLE_SEND);

		// Wait until MCU is done transferring.
		while(I2CMasterBusy(I2C0_BASE));

		//"close" variable argument list
		va_end(vdata);
	}

	//otherwise, we start transmission of multiple bytes on the
	//I2C bus
	else if(data_amount > 2)
	{
		//Initiate send of data from the MCU
		I2CMasterControl(I2C0_BASE, I2C_MASTER_CMD_BURST_SEND_START);

		// Wait until MCU is done transferring.
		while(I2CMasterBusy(I2C0_BASE));

		//send num_of_args-2 pieces of data, using the
		//BURST_SEND_CONT command of the I2C module
		for(i = 1; i < (data_amount - 1); i++)
		{
			//put next piece of data into I2C FIFO
			I2CMasterDataPut(I2C0_BASE, va_arg(vdata, int));
			//send next data that was just placed into FIFO
			I2CMasterControl(I2C0_BASE, I2C_MASTER_CMD_BURST_SEND_CONT);

			// Wait until MCU is done transferring.
			while(I2CMasterBusy(I2C0_BASE));
		}

		//put last piece of data into I2C FIFO
		I2CMasterDataPut(I2C0_BASE, va_arg(vdata, int));
		//send next data that was just placed into FIFO
		I2CMasterControl(I2C0_BASE, I2C_MASTER_CMD_BURST_SEND_FINISH);
		// Wait until MCU is done transferring.
		while(I2CMasterBusy(I2C0_BASE));

		//"close" variable args list
		va_end(vdata);
	}
}

int getI2C(int slave_addr, int reg)
{
	//we first have to write the address to the i2c line to specify which slave we want to read from.
	//false = write; true = read
	I2CMasterSlaveAddrSet(I2C0_BASE, slave_addr, false);

	//what register do you want to read
	I2CMasterDataPut(I2C0_BASE, reg);

	//send the register data to the slave
	I2CMasterControl(I2C0_BASE, I2C_MASTER_CMD_SINGLE_SEND);

	//wait for MCU to finish transaction
	while(I2CMasterBusy(I2C0_BASE));

	//specify that we are going to read from slave device
	I2CMasterSlaveAddrSet(I2C0_BASE, slave_addr, true);

	//send control byte and read from the register we specified
	I2CMasterControl(I2C0_BASE, I2C_MASTER_CMD_SINGLE_RECEIVE);

	//wait for MCU to finish transaction
	while(I2CMasterBusy(I2C0_BASE));

	//return data pulled from the specified register
	return I2CMasterDataGet(I2C0_BASE);
}
