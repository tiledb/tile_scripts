#!/usr/bin/env python3
import time
import Herakles
from db_ppr_ipbus import *
import plotext as tplt

# ------------------ CONFIG ------------------

HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer  = "192.168.0.3"

nsamp = 16
nchanperMD = 12
nMD = 1
firstMD = 0

bcid_l1a = 2246

# read_interval = 2.0  # seconds between read cycles

# ------------------ FULL SAMPLE HEATMAP ------------------

def print_heatmap_hg_lg(md, hg_data, lg_data,
                        nchanperMD=12,
                        nsamp=16,
                        vmin=0, vmax=4095):

    def value_to_color(val):
        """
        Map ADC value to 256-color background.
        Blue → Green → Yellow → Red
        """
        val = max(vmin, min(vmax, val))
        norm = (val - vmin) / (vmax - vmin)
        color_code = int(21 + norm * (196 - 21))
        return f"\033[48;5;{color_code}m"

    reset = "\033[0m"

    # Header row
    header = "Ch  | Gain | "
    for s in range(nsamp):
        header += f"{s:4d} "
    print(header)
    print("-" * len(header))

    # Channel rows (HG + LG)
    for ch in range(nchanperMD):
        idx = md * nchanperMD + ch

        # ---------- HG ----------
        row = f"{ch:02d}  | HG   | "
        for val in hg_data[idx]:
            color = value_to_color(val)
            row += f"{color}{val:4d}{reset} "
        print(row)

        # ---------- LG ----------
        row = f"{ch:02d}  | LG   | "
        for val in lg_data[idx]:
            color = value_to_color(val)
            row += f"{color}{val:4d}{reset} "
        print(row)

    print()

# ------------------ INITIALIZATION ------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = Herakles.Uhal(
    f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001"
)
ppr = PPr(ipbus)
feb = FEB(ppr)

print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")

# X axis (sample index)
step_x = list(range(nsamp))

# ------------------ READOUT LOOP ------------------

print("\nStarting continuous readout (Ctrl+C to stop)...\n")

try:

    # Send L1A trigger
    feb.send_L1A(bcid_l1a, 3)

    # Storage for this cycle
    all_hg_data = [[] for _ in range(nchanperMD * nMD)]
    all_lg_data = [[] for _ in range(nchanperMD * nMD)]

    # Read all channels
    for md in range(firstMD, firstMD + nMD):
        for ch in range(nchanperMD):

            hg = ppr.get_data_HG(md, ch, nsamp)
            lg = ppr.get_data_LG(md, ch, nsamp)

            idx = md * nchanperMD + ch
            all_hg_data[idx] = list(hg)
            all_lg_data[idx] = list(lg)

    # Clear terminal
    print("\033[H\033[J", end="")

    # Print heatmaps
    for md in range(firstMD, firstMD + nMD):
        print(f"\n========== MD{md} HG / LG SAMPLE HEATMAP ==========")
        print_heatmap_hg_lg(md,
                            all_hg_data,
                            all_lg_data,
                            nchanperMD=nchanperMD,
                            nsamp=nsamp,
                            vmin=0,
                            vmax=4095)



except KeyboardInterrupt:
    print("\nReadout stopped.")
