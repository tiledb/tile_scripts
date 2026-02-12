#!/usr/bin/env python3
from db_lib import *
from db_ppr_ipbus import IPbus
import sys
import time
import argparse

# -------------------- ARGUMENTS --------------------
parser = argparse.ArgumentParser(description="Read PPr registers, KU DNA, and XADC values")
parser.add_argument("-m", "--minidrawer", help="minidrawer: 1 to 4", type=int, default=1)
parser.add_argument("-e", "--evaluate", help="evaluate data", action="store_true")
parser.add_argument("-t", "--threshold", help="highlight threshold", type=float, default=2000)
args = parser.parse_args()

md = args.minidrawer - 1
if not (0 <= md <= 3):
    print("The number of md must be from 1 to 4")
    sys.exit(-1)

THRESHOLD = args.threshold

# -------------------- COLORS --------------------
class color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    END = '\033[0m'

# -------------------- IPBUS --------------------
controlhub_ipaddress = "192.168.0.201"
ppr_ipaddress = "192.168.0.2"
ppr = IPbus(controlhub_ipaddress, ppr_ipaddress)
fw_ver = ppr.ReadVal(1)
print(f"Connected to PPr with IP: {ppr_ipaddress}, FW version: {hex(fw_ver)}\n")

# -------------------- CONFIG REGISTERS --------------------
for cfg_idx, addr in enumerate(lut_cfgbus_address):
    data = ppr.DB_Read_Val(0, addr)
    print(f"{lut_cfgbus_address_labels[cfg_idx]} -> {bin(data[0])} <-> {bin(data[1])}")
print("-" * 120)

# -------------------- PREPARE PRINT BLOCK --------------------
num_xadc = len(lut_xadc_address)
num_ku_lines = 2  # FPGA A and B
num_block_lines = 1 + num_ku_lines + num_xadc  # 1 loopback + KU DNA/status + XADC lines

# Print initial empty lines so we can overwrite them
print("\n" * num_block_lines, end='')

i = 0
while True:
    # -------------------- LOOPBACK --------------------
    ppr.DB_Write_Val(md, 0, cfb_loopback, i, 0)
    time.sleep(0.1)
    loopback_value = ppr.DB_Read_Val(md, lut_cfgbus_address[cfb_loopback])
    sent_line = f"\033[1;32mSent value: {hex(i)} Received Values: {hex(loopback_value[0])} - {hex(loopback_value[1])}\033[0m"

    # -------------------- KU DNA & STATUS --------------------
    dna_data_array = [
        ppr.DB_Read_Val(md, lut_tx_address[c_stb_dna_2]),
        ppr.DB_Read_Val(md, lut_tx_address[c_stb_dna_1]),
        ppr.DB_Read_Val(md, lut_tx_address[c_stb_dna_0])
    ]
    running_time = ppr.DB_Read_Val(md, lut_tx_address[c_stb_running_time_status])
    db_reg_buff = ppr.DB_Read_Val(md, lut_tx_address[c_stb_pgood_reg])

    ku_lines = []
    # Format KU FPGA A
    ku_lines.append(
        f"KU FPGA A -> DNA0: {dna_data_array[0][0]} ~ {dna_data_array[0][0]} "
        f"DNA1: {dna_data_array[1][0]} ~ {dna_data_array[1][0]} "
        f"DNA2: {dna_data_array[2][0]} ~ {dna_data_array[2][0]} "
        f"Running: {running_time[0]} ~ {running_time[0]} "
        f"Side: {(db_reg_buff[0]>>27)&0b1} Switches: {(db_reg_buff[0]>>28)&0b1111}"
    )
    # Format KU FPGA B
    ku_lines.append(
        f"KU FPGA B -> DNA0: {dna_data_array[0][1]} ~ {dna_data_array[0][1]} "
        f"DNA1: {dna_data_array[1][1]} ~ {dna_data_array[1][1]} "
        f"DNA2: {dna_data_array[2][1]} ~ {dna_data_array[2][1]} "
        f"Running: {running_time[1]} ~ {running_time[1]} "
        f"Side: {(db_reg_buff[1]>>27)&0b1} Switches: {(db_reg_buff[1]>>28)&0b1111}"
    )

    # -------------------- XADC READINGS --------------------
    xadc_lines = []
    for xadc_idx, addr in enumerate(lut_xadc_address):
        full_addr = 0xA00 | addr
        data = ppr.DB_Read_Val(md, full_addr)
        side_a = data[0]
        side_b = data[1]

        side_a_eval = side_a * lut_xadc_fa[xadc_idx] + lut_xadc_fb[xadc_idx]
        side_b_eval = side_b * lut_xadc_fa[xadc_idx] + lut_xadc_fb[xadc_idx]
        side_a_reeval = side_a_eval * lut_xadc_fg[xadc_idx]
        side_b_reeval = side_b_eval * lut_xadc_fg[xadc_idx]

        if not args.evaluate:
            line = f"{hex(full_addr)} -> {lut_xadc_address_labels[xadc_idx]} -> {side_a} ~ {side_a_eval:.2f}{lut_xadc_dimensions[xadc_idx]} <-> {side_b} ~ {side_b_eval:.2f}{lut_xadc_dimensions[xadc_idx]}"
        else:
            line = f"{hex(full_addr)} -> {lut_xadc_address_labels[xadc_idx]} -> {side_a} ~ {side_a_eval:.2f}{lut_xadc_dimensions[xadc_idx]} ~ {side_a_reeval:.2f}{lut_xadc_fg_dimensions[xadc_idx]} <-> {side_b} ~ {side_b_eval:.2f}{lut_xadc_dimensions[xadc_idx]} ~ {side_b_reeval:.2f}{lut_xadc_fg_dimensions[xadc_idx]}"
        xadc_lines.append(line)

    # -------------------- PRINT BLOCK --------------------
    print(f"\033[{num_block_lines}F", end='')  # Move cursor up to start of block
    print("\033[K" + sent_line)               # Clear line + loopback
    for line in ku_lines:
        print("\033[K" + line)                # Clear line + KU DNA/status
    for line in xadc_lines:
        print("\033[K" + line)                # Clear line + XADC

    i += 1
    time.sleep(5)
