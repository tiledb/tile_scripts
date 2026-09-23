#!/usr/bin/env python
#tilecal libs
from db_lib import *
from db_ppr_ipbus import *

#python libs
import sys, time
import Herakles
from optparse import OptionParser

    
parser = OptionParser()
parser.add_option("-m", "--minidrawer", help="minidrawer number", dest='minidrawer', type='string', action="store")
parser.add_option("-f", "--fpga", help="fpga side", dest='fpga', type='string', action="store")
parser.add_option("-r", "--register", help="register number", dest='register', type='string', action="store")
parser.add_option("-w", "--write", help="register value", dest='write', type='string', action="store")
parser.add_option("-z", "--zorro", help="mask value", dest='zorro', type='string', action="store")
parser.add_option("-b", "--bcid", help="bcid value", dest='bcid', type='string', action="store")
parser.add_option('-s', '--sync',  action = 'store_true')
parser.add_option('-c', '--syncclear',  action = 'store_true')
parser.add_option('-e', '--test',  action = 'store_true')
parser.add_option('-p', '--persistent',  action = 'store_true')
parser.add_option("-l", "--list", help="list the library definitions", dest='list', type='string', action="store")
parser.add_option("-a", "--aim", help="aims an specific bit", dest='aim', type='string', action="store")

parser.add_option("--ppripaddress", help="sets ipaddress of the ppr", dest='ppripaddress', type='string', action="store")
parser.add_option("--hostipaddress", help="sets ipaddress of the host", dest='hostipaddress', type='string', action="store")

(options, args) = parser.parse_args()


print('communicating with host')
if options.ppripaddress is None:
    PPrIPaddressServer="192.168.0.3"
    print("No ipaddress... defaulting to", PPrIPaddressServer , "...")
    
else:
    PPrIPaddressServer=options.ppripaddress

if options.hostipaddress is None:
    HostIPaddressServer="192.168.0.201"
    print("No host ipaddress... defaulting to", HostIPaddressServer , "...")
    
else:
    HostIPaddressServer=options.hostipaddress

ppr = IPbus(HostIPaddressServer,PPrIPaddressServer)
print("Connected to PPr with ip: " + PPrIPaddressServer + ", FW version: " + str(hex(ppr.ReadVal(1))))


if options.syncclear:  
    print("Clearing sync commands...")
    ppr.SyncClear()
    exit(0)

if options.list is None:
    print("Library parsed...")
else:
    print("Parsing library contents...")
    if options.list == "tx":
        for i in range(len(lut_tx_address)):
            print( str(i)+ " -> \t"+ hex(lut_tx_address[i]) + " -> \t" + lut_tx_address_labels[i] )
    elif options.list == "rx":
        for i in range(len(lut_cfgbus_address)):
            print( str(i)+ " -> \t"+ hex(lut_cfgbus_address[i]) + " -> \t" + lut_cfgbus_address_labels[i] )
    elif options.list == "xadc":
        for i in range(len(lut_xadc_address)):
            print( str(i)+ " -> \t"+ hex(lut_xadc_address[i]) + " -> \t" + lut_xadc_address_labels[i] )
    exit(0)
    
if options.test:
    print('Communicating with PPREmu')
    r=0
    v=0
    for r in range(16):
        #for v in range(16):
        v=r;
        print("Writing value: ", v ," in register: ", r )
        ppr.AsyncWrite(0,r,v)
    exit(-1)
    
#fpga=format_number(options.fpga)
fpga=0
if (options.fpga=="A"):
    fpga=2
elif (options.fpga=="B"):
    fpga=3
else:
    print("No FPGA chosen... broadcasting...")
    

md=0    
if options.minidrawer is None:
    print("No minidrawer, defaulting to 1")
else:
    md=format_number(options.minidrawer)-1
    
if options.register is None:
    print("No reg?")
    exit(-1)
else:
    the_register=format_number(options.register)

if the_register<len(lut_cfgbus_address_labels):
    if the_register in lut_cfgbus_address:
        the_read_register= lut_cfgbus_address[the_register] & 0xFF | 0xC00
        the_register_label=lut_cfgbus_address_labels[the_register]
        print("Register: "+ str(the_register) +" found in in library as: " + the_register_label)
    else:
        the_read_register= lut_cfgbus_address[the_register] & 0xFF | 0xC00
        the_register_label=lut_cfgbus_address_labels[the_register]
        print("Warning: Register "+ str(the_register) +" corresponds to:"+ the_register_label)
else:
    try:
        the_read_register= lut_cfgbus_address[the_register] & 0xFF | 0xC00
        the_register_label=lut_cfgbus_address_labels[(lut_cfgbus_address.index(the_register))]
        print("Register: "+ str(the_register) +" found in in library as: " + the_register_label)
    except:
        the_read_register= the_register
        the_register_label="(Not in library)"


the_read_register=the_register

the_mask=0
if options.zorro is None:
    print("No mask chosen... Use -z or --zorro and value to introduce a mask...")
else:
    the_mask = format_number(options.zorro)
    
    
                    
if options.write is None:
	
	while True:
	
		if options.fpga == "A":
			the_read_value_sidea = (ppr.DB_Read_Val(md,the_read_register)[0])
			the_read_value= hex(the_read_value_sidea) + " -> " + str(the_read_value_sidea)
		elif options.fpga == "B":
			the_read_value_sideb = (ppr.DB_Read_Val(md,the_read_register)[1])
			the_read_value= hex(the_read_value_sidea) + " -> " + str(the_read_value_sidea)
		else:
			the_read_value_sidea = (ppr.DB_Read_Val(md,the_read_register)[0])
			the_read_value_sideb = (ppr.DB_Read_Val(md,the_read_register)[1])
			the_read_value= hex(the_read_value_sidea) + " -> " + str(the_read_value_sidea) + " - " + hex(the_read_value_sideb) + " -> " + str(the_read_value_sideb)
		    #the_read_value=hex(ppr.DB_Read_Val(0,the_read_register)[0])+" - "+hex(ppr.DB_Read_Val(0,the_read_register)[1])
		
		print("Asyncronous Reading of MD: "+ str(md+1) + ", DB register: ("+ hex(the_read_register) +  ")" + " - " + the_register_label + " " + " value: "+ str(the_read_value) + " -> "  + " ...")
		if options.persistent is None:
			break
      
else:
    if options.aim is None:
        the_value=format_number(options.write)
    else:
        the_aim = format_number(options.aim)
        the_value=format_number(options.write)<<the_aim
    
    if (options.sync):
        if options.bcid is None:
            print("No BCID?")
            exit(-1)
        else:
            the_bcid=format_number(options.bcid)
            print("Syncronous Writing ", "DB register" , the_register , ", with value:", the_value , ", at BCID: " , the_bcid ,"...")
            ppr.SyncWrite(the_bcid,0,the_value)

            
    else:
        
        print("Asyncronous Writing to MD: ", md+1 , ", DB register: ", the_register ,  ", with value: ", hex(the_value), " ...")
        #ipbus. AsyncWrite(1,the_register,the_value)
        #ipbus.AsyncWrite(md,0x1, (1<<22)+(FPGA<<18)+(card<<16)+(command<<12)+data)
        
        #the_read_register= lut_cfgbus_address[the_register] & 0xFF | 0xC00
        ppr.DB_Write_Val(md,fpga,the_register,the_value,the_mask)
        
        if options.fpga == "A":
            the_read_value_sidea = (ppr.DB_Read_Val(md,the_read_register)[0])
            the_read_value= hex(the_read_value_sidea) + " -> " + str(the_read_value_sidea)
        elif options.fpga == "B":
            the_read_value_sideb = (ppr.DB_Read_Val(md,the_read_register)[1])
            the_read_value= hex(the_read_value_sidea) + " -> " + str(the_read_value_sidea)
        else:
            the_read_value_sidea = (ppr.DB_Read_Val(md,the_read_register)[0])
            the_read_value_sideb = (ppr.DB_Read_Val(md,the_read_register)[1])
            the_read_value= hex(the_read_value_sidea) + " -> " + str(the_read_value_sidea) + " - " + hex(the_read_value_sideb) + " -> " + str(the_read_value_sideb)
            #the_read_value=hex(ppr.DB_Read_Val(0,the_read_register)[0])+" - "+hex(ppr.DB_Read_Val(0,the_read_register)[1])
        
        print("Asyncronous Reading of MD: ", md+1 , ", DB register: (", hex(the_read_register) ,  ")", " - ", the_register_label , " " ," value: ", " -> " ,  the_read_value, " ...")
