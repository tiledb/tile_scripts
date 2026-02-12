#!/usr/bin/env python3

import time
import Herakles
from db_ppr_ipbus import IPbus   # adjust import path if needed

threshold = 0x11C

class color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    END = '\033[0m'

# --------------------------------------------------
# Connect
# --------------------------------------------------
ipb = IPbus(
    controlhub_ipaddress="192.168.0.201",
    ppr_ipaddress="192.168.0.2",
    verbose=False
)

# --------------------------------------------------
# Read meta info
# --------------------------------------------------
meta = ipb.ReadVal(0x9F)

# Enable deadtime
Reg5 = ipb.ReadVal(0x5)
# ipb.RODConfigWrite(0x5, Reg5 | 0x8)

# Read counters
L1A          = ipb.ReadVal(0xA)
EventNumber = ipb.ReadVal(0xB)
bcid        = ipb.ReadVal(0x9D)
ttype       = ipb.ReadVal(0x9F)

# --------------------------------------------------
# Configure trigger type
# --------------------------------------------------
Reg3 = ipb.ReadVal(0x3)
Reg3 &= 0xFF00FFFF

mytt = 0
ena = 1

# ipb.RODConfigWrite(
#     0x3,
#     (ena << 31) | (mytt << 16) | Reg3
# )

Reg3 = ipb.ReadVal(0x3)

print("Reg3:", hex(Reg3))
print("L1As:", L1A, "EventNumber:", EventNumber,
      "Trigger Type:", ttype, "Expected:", mytt)

print(
    "Correct Trigger Type"
    if ttype == mytt
    else "Incorrect Trigger Type"
)

# --------------------------------------------------
# Decode meta
# --------------------------------------------------
nsmp  = 16
nchan = 1

print(f"meta: 0x{meta:x}  nchan: {nchan}  nsamps: {nsmp}")

# --------------------------------------------------
# Read samples
# --------------------------------------------------
for chan in range(nchan):

    # Raw read (same address logic as original)
    samples = ipb.ipbus.Read(0x100 + (32 * chan), nsmp)

    samplesLG = [(v & 0xFFF) for v in samples]
    samplesHG = [((v >> 16) & 0xFFF) for v in samples]

    print(f"\nChannel {chan+1}  BCID: {bcid}")

    print("LG:", end=" ")
    for s in samplesLG:
        if s > threshold:
            print(color.RED + f"{s:3d}" + color.END, end=" ")
        else:
            print(f"{s:3d}", end=" ")
    print()

    print("HG:", end=" ")
    for s in samplesHG:
        if s > threshold:
            print(color.GREEN + f"{s:3d}" + color.END, end=" ")
        else:
            print(f"{s:3d}", end=" ")
    print()

# --------------------------------------------------
# Disable deadtime (optional)
# --------------------------------------------------
print("BCID:", ipb.ReadVal(0x9D))
print("BCID+1:", ipb.ReadVal(0x9E))
