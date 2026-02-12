#!/usr/bin/env python3
import time
import random
from array import array
import plotly.graph_objects as go
from db_ppr_ipbus import IPbus
import os
import argparse
from datetime import datetime

# -------------------- ARGUMENTS --------------------
parser = argparse.ArgumentParser(description="PPR ADC Test Plotter")
parser.add_argument("-f", "--folder", type=str, default="./plots", help="Folder to save plots")
parser.add_argument("-t", "--timestamp", action="store_true", help="Prepend datetime stamp to filenames")
args = parser.parse_args()

# Ensure folder exists
os.makedirs(args.folder, exist_ok=True)

# -------------------- CONFIG --------------------
IPaddressServer = "192.168.0.201"
PPR_IP = "192.168.0.2"
verbose = False

nsamp = 16
loop = 1  # number of iterations
charge = 0xa0
nchanperMD = 12  # channels per minidrawer
nsteps = 10

# Number of Minidrawers
nMD = 4
firstMD = 1
ntrials = 4

# A side
chan_id = [0x530000] * nchanperMD
RBack_CMDtoOffset = [0, 1, 999, 999, 999, 999, 999, 999, 4, 5, 2, 3]

total_cmd = 0
error_cmd = 0

# -------------------- INITIALIZE --------------------
print("Communicating with host...")
ipbus = IPbus(IPaddressServer, PPR_IP, verbose=verbose)
print("Communication successful.")

stableP = 1650
stableM = 2530
StepDAC = 1000 / nsteps
valDACList = [i * int(StepDAC) for i in range(nsteps)]
valDAC = list(valDACList)  # Convert to list

# Disable TTC and Deadtime
ipbus.RODConfigWrite(0x5, 0x0)
time.sleep(0.01)

# Read N_samples and N_chan
N_samples = 0xFF & ipbus.ReadVal(0x9F)
N_chan = 48  # forced as before

# -------------------- PREP AVG ARRAYS --------------------
nDAC = len(valDAC)
avgHG = [[0.0 for _ in range(nDAC)] for _ in range(nchanperMD * nMD)]
avgLG = [[0.0 for _ in range(nDAC)] for _ in range(nchanperMD * nMD)]

total_lg_errors = [[0 for _ in range(nchanperMD)] for _ in range(4)]
total_hg_errors = [[0 for _ in range(nchanperMD)] for _ in range(4)]

# -------------------- MAIN LOOP --------------------
for i in range(nDAC):
    chargeP = stableP + valDAC[i]
    chargeM = stableM - valDAC[i]

    print(f"# New DAC step {i}: {valDAC[i]}")

    for md in range(firstMD, firstMD + nMD):
        for adc in range(nchanperMD):
            if verbose:
                print(f"+++++ ADC is : {adc}")
            FPGA = ((adc // 6) << 1) + (adc % 2)
            card = (adc // 2) % 3

            # HIGH GAIN and LOW GAIN writes
            for charge_val, setting in [(chargeP, 0xA), (chargeM, 0xB), (chargeP, 0x8), (chargeM, 0x9)]:
                for trial in range(ntrials):
                    ipbus.AsyncWrite(md, 0x1, 0x8000000)
                    time.sleep(0.0001)
                    cmd_val = (1 << 22) + (FPGA << 18) + (card << 16) + (setting << 12) + int(charge_val)
                    ipbus.AsyncWrite(md, 0x1, cmd_val)
                    total_cmd += 1
                    time.sleep(0.0001)
                    ipbus.AsyncWrite(md, 0x1, 0x8000000)
                    if ipbus.CheckValue(md, FPGA, card, setting, charge_val, verbose=verbose):
                        break
                    if trial == ntrials - 1:
                        error_cmd += 1

# -------------------- READ DATA --------------------
for md in range(firstMD, firstMD + nMD):
    for adc in range(nchanperMD):
        hg_addr = ((md * nchanperMD + adc) * 32 + 0x100)
        lg_addr = ((md * nchanperMD + adc) * 32 + 0x700)

        hg = list(ipbus.RODReadChunck(hg_addr, nsamp))
        lg = list(ipbus.RODReadChunck(lg_addr, nsamp))

        sumhg = 0
        sumlg = 0
        hg_err = 0
        lg_err = 0

        for a in range(len(hg)):
            if hg[a] & 0x1000:
                total_hg_errors[md][adc] += 1
            else:
                sumhg += hg[a] & 0xFFF

            if lg[a] & 0x1000:
                total_lg_errors[md][adc] += 1
            else:
                sumlg += lg[a] & 0xFFF

        idx = adc + (md - firstMD) * nchanperMD
        avgHG[idx].append(sumhg / max(len(hg) - hg_err, 1))
        avgLG[idx].append(sumlg / max(len(lg) - lg_err, 1))

# -------------------- PLOT WITH PLOTLY --------------------
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_") if args.timestamp else ""

for md in range(nMD):
    for adc in range(nchanperMD):
        x = valDAC
        yhg = avgHG[adc + (md - firstMD) * nchanperMD]
        ylg = avgLG[adc + (md - firstMD) * nchanperMD]

        # High Gain plot
        fig_hg = go.Figure()
        fig_hg.add_trace(go.Scatter(x=x, y=yhg, mode='lines+markers', name=f"HG ADC {adc} MD {md}"))
        fig_hg.update_layout(title=f"High Gain - ADC {adc} MD {md}",
                             xaxis_title="DAC value",
                             yaxis_title="ADC counts")
        fig_hg.write_image(os.path.join(args.folder, f"{timestamp}HG_ADC{adc}_MD{md}.png"))

        # Low Gain plot
        fig_lg = go.Figure()
        fig_lg.add_trace(go.Scatter(x=x, y=ylg, mode='lines+markers', name=f"LG ADC {adc} MD {md}"))
        fig_lg.update_layout(title=f"Low Gain - ADC {adc} MD {md}",
                             xaxis_title="DAC value",
                             yaxis_title="ADC counts")
        fig_lg.write_image(os.path.join(args.folder, f"{timestamp}LG_ADC{adc}_MD{md}.png"))

# -------------------- FINAL REPORT --------------------
print("Test finished.")
print("Total commands=", total_cmd, "  with error detected:", error_cmd)

for md in range(nMD):
    for i in range(nchanperMD):
        print(f"MD={md} chan={i} CRC Errors. "
              f"HG={total_hg_errors[md][i]} "
              f"{float(total_hg_errors[md][i] * 100) / (nDAC * nsamp):.2f}% "
              f"LG={total_lg_errors[md][i]} "
              f"{float(total_lg_errors[md][i] * 100) / (nDAC * nsamp):.2f}%")
