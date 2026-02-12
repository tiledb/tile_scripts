#!/usr/bin/env python

import os
import sys
import Herakles
import socket


threshold=0x11C
class color:
   PURPLE = '\033[95m'
   CYAN = '\033[96m'
   DARKCYAN = '\033[36m'
   BLUE = '\033[94m'
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

uhal = Herakles.Uhal("tcp://192.168.0.201:10203?target=192.168.0.2:50001")
meta = uhal.Read(0x9F)

## Enable the deadtime
Reg5=uhal.Read(0x5)
uhal.Write(0x5,Reg5 | 0x8)  

L1A=uhal.Read(0xA)
EventNumber=uhal.Read(0xB)
bcid=uhal.Read(0x9D)
ttype=uhal.Read(0x9F)
Reg3=uhal.Read(0x3)
Reg3 = Reg3 & 0xFF00FFFF
#mytt = 130
mytt = 0
print(hex(Reg3))
print(hex((mytt << 16)))
ena = 1
uhal.Write(0x3,((ena<<31) | (mytt<<16) | Reg3))
Reg3=uhal.Read(0x3)
print ("Reg3 ", hex(Reg3))
print ("L1As=",L1A, " EventNumber:", EventNumber, " Trigger Type:", ttype, " Expected Trigger Type", mytt)
if ttype == mytt:
   print ("Correct Trigger Type: Data should be updated")
else:
   print ("Incorrect Trigger Type: Data should NOT be updated")


nsmp = meta & 0xFF;
nsmp = 16
nchn = (meta >> 8) & 0xFF
print ("meta: 0x%x nchan: %i nsamps: %i" % (meta,nchn,nsmp))
samplesLG=[]
samplesHG=[]
#for i in xrange(nchn):
nchan=24
firstMD = 0
for i in range(12*firstMD,12*firstMD + nchan):
    samples = uhal.Read(0x100+(32*i),nsmp)

#    if i == 11: 
#       print(samples)
#       print(hex(0x100+32*i))
    samplesLG = [(value&0xFFF)/1 for value in samples]
    samplesHG = [((value>>16)&0xFFF)/1 for value in samples]
    print ((i+1) ," == BCID:",bcid)
    print ("LG: "),
    pedLG = 0
    pedHG = 0
    #for s in xrange(32):
    #  pedLG = (samplesLG[s]&0xFFF) + pedLG
    #  pedHG = (samplesHG[s]&0xFFF) + pedHG
    #pedLG = pedLG/32
    #pedHG = pedHG/32
    for s in range(nsmp):
        if ( ((int(samplesLG[s])&0xFFF)-pedLG)>(threshold)):
            print (color.RED + "%3d" % ((samplesLG[s] & 0xFFF)-pedLG) + color.END),
        else:
            print ("%3d" % ((int(samplesLG[s]) & 0xFFF)-pedLG)),           
    print("")
    print("HG: "), 
    
    for s in range(nsmp):
        if ( ((int(samplesHG[s])&0xFFF)-pedHG)>(threshold)):
            print (color.GREEN + "%3d" % ((int(samplesHG[s]) & 0xFFF)-pedHG) + color.END),
        else:
            print ("%3d" % ((int(samplesHG[s]) & 0xFFF)-pedHG)),           
    print("")

#Disable the deadtime
print(uhal.Read(0x9D))
print(uhal.Read(0x9E))
        #ss = "%s %3x" % (ss, vsmp[c*nsmp+s] & 0xFFF)
    #print ss


