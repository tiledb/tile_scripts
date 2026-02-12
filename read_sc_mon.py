#!/usr/bin/env python3
# tilecal libs
from db_lib import *
from db_ppr_ipbus import IPbus

# python libs
import sys
import time
import argparse

# -------------------- ARGUMENTS --------------------
parser = argparse.ArgumentParser(description="Read XADC values from PPr and optionally evaluate")
parser.add_argument("-m", "--minidrawer", help="minidrawer: 1 to 4", type=int, default=1)
parser.add_argument("-e", "--evaluate", help="evaluate data", action="store_true")
parser.add_argument("-t", "--threshold", help="highlight threshold", type=float, default=2000)
args = parser.parse_args()

md = args.minidrawer - 1
if not (0 <= md <= 3):
    print("The number of md must be from 1 to 4")
    sys.exit(-1)

THRESHOLD = args.threshold

# -------------------- COLOR DEFINITIONS --------------------
class color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    END = '\033[0m'

# -------------------- IPBUS CONNECTION --------------------
controlhub_ipaddress = "192.168.0.201"
ppr_ipaddress = "192.168.0.2"
ppr = IPbus(controlhub_ipaddress, ppr_ipaddress)
fw_ver = ppr.ReadVal(1)
print(f"Connected to PPr with IP: {ppr_ipaddress}, FW version: {hex(fw_ver)}")

# -------------------- READ LUT CONFIG --------------------
for cfgbus_address in range(len(lut_cfgbus_address)):
    data = ppr.DB_Read_Val(0, lut_cfgbus_address[cfgbus_address])
    side_a = data[0]
    side_b = data[1]
    line = f"{lut_cfgbus_address_labels[cfgbus_address]} -> {bin(side_a)} <-> {bin(side_b)}"
    print(line)

print("-----------------------------------------------------------------------------------------------------------------")

# -------------------- MAIN LOOP --------------------
i = 0
num_xadc_lines = len(lut_xadc_address)
total_lines = 1 + num_xadc_lines  # 1 for Sent value + XADC lines

# Print initial empty lines for proper cursor movement
print("\n" * total_lines, end='')

while True:
    # -------------------- LOOPBACK --------------------
    ppr.DB_Write_Val(md, 0, cfb_loopback, i, 0)
    time.sleep(0.1)
    loopback_value = ppr.DB_Read_Val(md, lut_cfgbus_address[cfb_loopback])
    sent_line = f"\033[1;32mSent value: {hex(i)} Received Values: {hex(loopback_value[0])} - {hex(loopback_value[1])}\033[0m"

    # -------------------- XADC READINGS --------------------
    xadc_lines = []
    for xadc_idx, xadc_address in enumerate(lut_xadc_address):
        addr = 0xA00 | xadc_address
        data = ppr.DB_Read_Val(md, addr)
        side_a = data[0]
        side_b = data[1]

        # Apply LUT conversions
        side_a_eval = side_a * lut_xadc_fa[xadc_idx] + lut_xadc_fb[xadc_idx]
        side_b_eval = side_b * lut_xadc_fa[xadc_idx] + lut_xadc_fb[xadc_idx]
        side_a_reeval = side_a_eval * lut_xadc_fg[xadc_idx]
        side_b_reeval = side_b_eval * lut_xadc_fg[xadc_idx]

        # Format output line
        if not args.evaluate:
            line = (f"{hex(addr)} -> {lut_xadc_address_labels[xadc_idx]} "
                    f"-> {side_a} ~ {side_a_eval:.2f}{lut_xadc_dimensions[xadc_idx]} "
                    f"<-> {side_b} ~ {side_b_eval:.2f}{lut_xadc_dimensions[xadc_idx]}")
        else:
            line = (f"{hex(addr)} -> {lut_xadc_address_labels[xadc_idx]} "
                    f"-> {side_a} ~ {side_a_eval:.2f}{lut_xadc_dimensions[xadc_idx]} ~ {side_a_reeval:.2f}{lut_xadc_fg_dimensions[xadc_idx]} "
                    f"<-> {side_b} ~ {side_b_eval:.2f}{lut_xadc_dimensions[xadc_idx]} ~ {side_b_reeval:.2f}{lut_xadc_fg_dimensions[xadc_idx]}")
        xadc_lines.append(line)

    # -------------------- MOVE CURSOR AND CLEAR --------------------
    print(f"\033[{total_lines}F", end='')  # Move cursor up to start of block
    print("\033[K" + sent_line)            # Clear line + print loopback
    for line in xadc_lines:
        print("\033[K" + line)             # Clear each line + print new XADC line

    i += 1
    time.sleep(5)
