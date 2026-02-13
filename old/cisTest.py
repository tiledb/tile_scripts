#!/usr/bin/env python3
import time
import os
import Herakles
from array import array
from db_ppr_ipbus import PPr, FEB, PPrReg

import plotext as tplt
import math


# -----Scientific functions-----

def analyze_pulse(samples,
                  pedestal_samples=4,
                  noise_sigma_threshold=5,
                  threshold_fraction=0.5):
    """
    Robust pulse analysis.

    Returns:
        pedestal
        peak_value
        peak_index
        center_of_mass
        fwhm
    If no pulse is detected → returns pedestal and 0s.
    """

    if not samples or len(samples) < pedestal_samples + 2:
        return 0, 0, 0, 0, 0

    # -------------------------------------------------
    # 1) Pedestal estimation (mean of first N samples)
    # -------------------------------------------------
    pedestal_region = samples[:pedestal_samples]
    pedestal = sum(pedestal_region) / pedestal_samples

    # Estimate noise sigma from pedestal region
    variance = sum((x - pedestal) ** 2 for x in pedestal_region) / pedestal_samples
    noise_sigma = math.sqrt(variance)

    # -------------------------------------------------
    # 2) Subtract pedestal
    # -------------------------------------------------
    signal = [x - pedestal for x in samples]

    peak_value = max(signal)
    peak_index = signal.index(peak_value)

    # -------------------------------------------------
    # 3) Pulse existence check
    # -------------------------------------------------
    # Require peak to be significantly above noise
    if noise_sigma == 0 or peak_value < noise_sigma_threshold * noise_sigma:
        return pedestal, 0, 0, 0, 0

    # -------------------------------------------------
    # 4) Center of mass
    # -------------------------------------------------
    total = sum(signal)
    if total > 0:
        center_of_mass = sum(i * v for i, v in enumerate(signal)) / total
    else:
        center_of_mass = 0

    # -------------------------------------------------
    # 5) FWHM
    # -------------------------------------------------
    half_max = peak_value * threshold_fraction
    above_half = [i for i, v in enumerate(signal) if v >= half_max]

    if len(above_half) >= 2:
        fwhm = above_half[-1] - above_half[0]
    else:
        fwhm = 0

    return pedestal, peak_value, peak_index, center_of_mass, fwhm


# ------------------ PLOTTING -------------------

def ascii_plot_md(md, avgHG, avgLG, nchanperMD=12):
    for ch in range(nchanperMD):
        idx = ch + md * nchanperMD
        tplt.clear_figure()
        tplt.plot(range(len(avgHG[idx])), list(avgHG[idx]), label=f"HG Ch{ch}")
        tplt.plot(range(len(avgLG[idx])), list(avgLG[idx]), label=f"LG Ch{ch}")
        tplt.title(f"MD{md} Ch{ch}")
        tplt.show()

def ascii_plot_grid(md, step_x, hg_data, lg_data, nchanperMD=12, ncols=6, nrows=2, width=20, height=20):
    """
    Arrange ASCII plots for MD channels in a grid with fixed subplot size.
    """
    plots = []

    # Create fixed-size ASCII plots
    for ch in range(nchanperMD):
        idx = ch + md * nchanperMD
        tplt.clear_figure()
        tplt.plot(list(step_x), list(hg_data[idx]), label="")
        tplt.plot(list(step_x), list(lg_data[idx]), label="")
        tplt.title(f"Ch{ch}")
        tplt.plotsize(width, height)   # fix width and height
        plot_str = tplt.build()        # get ASCII plot as string
        plots.append(plot_str.splitlines())

    # Pad each plot to exactly height lines
    for i in range(len(plots)):
        while len(plots[i]) < height:
            plots[i].append(" " * width)

    # Print the grid (ncols x nrows)
    for row_idx in range(nrows):
        row_plots = plots[row_idx*ncols : (row_idx+1)*ncols]
        for line_idx in range(height):
            print("  ".join(p[line_idx] for p in row_plots))
        print("\n")  # spacing after each row

# ------------------ CONFIG ------------------

HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

verbose = True
nsamp = 16
nchanperMD = 12
nMD = 4
firstMD = 0
step_events = 1

n_events = 1  # number of CIS events per step

#BCID parameters
bcid_l1a = 2246
BCID_charge = 500
BCID_discharge = 2200
gain = 0

min_DAC = 1278# 1650 #1278
max_DAC = 2261# 2300 #2261
ADCped = 100

# CIS DAC charge for test
DACcharge = 1500

# ------------------ INITIALIZATION -------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = Herakles.Uhal(f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001")
ppr = PPr(ipbus)
feb = FEB(ppr)

print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")

# Allocate arrays for storing CIS data
step_x = []  # injected step number
all_hg_data = [[] for _ in range(nchanperMD * nMD)]
all_lg_data = [[] for _ in range(nchanperMD * nMD)]

# ------------------ CONFIG PHASE -------------------

print("Setting TTC internal... ", end="")
ret = ppr.set_global_TTC_internal()
print("Ok" if ret else "Failed")

# print("Resetting CRC counters... ", end="")
# ret = ppr.reset_CRC_counters()
# print("Ok" if ret else "Failed")

# print("Reading CRC counters... ")
initial_crc_sideA = []
initial_crc_sideB = []
final_crc_sideA = []
final_crc_sideB = []

print("Initial CRC Counters")
print("=" * 40)
print(f"{'MD':<6}{'Side A':<15}{'Side B':<15}")
print("-" * 40)

for i in range(firstMD, firstMD + nMD):
    a = ppr.get_CRC_tot_errors(i, side="A")
    b = ppr.get_CRC_tot_errors(i, side="B")

    initial_crc_sideA.append(a)
    initial_crc_sideB.append(b)

    print(f"{f'MD{i}':<6}{a:<15}{b:<15}")

print("=" * 40)
print(f"{'Totals:':<6}{str(initial_crc_sideA):<15}{str(initial_crc_sideB):<15}")

print("Setting PPr enable deadtime bit in Global Trigger Conf...")
ret = ppr.set_global_trigger_deadtime(0)
print(f"  set bit to 0: {'Ok' if ret else 'Fail'}")
ret = ppr.set_global_trigger_deadtime(1)
print(f"  set bit to 1: {'Ok' if ret else 'Fail'}")



# ------------------ CIS TEST -------------------

print("==> Starting CIS test...")

# 1) Configure FEB ADC DACs
DACbiasP, DACbiasN = feb.convert_ped_ADC_to_DACs(ADCped)
 
print("Configuring FEB pedestal DACs... ", end="")
for md in range(firstMD, firstMD + nMD):
    for feb_id in range(nchanperMD):
        feb.set_ped_HG_pos(md, 0, feb_id, DACbiasP)
        feb.set_ped_HG_neg(md, 0, feb_id, DACbiasN)
        feb.set_ped_LG_pos(md, 0, feb_id, DACbiasP)
        feb.set_ped_LG_neg(md, 0, feb_id, DACbiasN)

        feb.load_ped_HG(md, 0, feb_id)
        feb.load_ped_LG(md, 0, feb_id)
print("Ok")

# 2) Set FEB switches
print("Setting FEB switches... ", end="")
for md in range(firstMD, firstMD + nMD):
    for adc in range(nchanperMD):
        ret = feb.set_switches_noise(md, dbside=2, feb=adc)

# 3) Set CIS BCID parameters
print("Setting CIS on minidrawers... ", end="")
for md in range(firstMD, firstMD + nMD):
    for feb_id in range(nchanperMD):
        feb.set_CIS_BCID_settings(md, 0, BCID_charge, BCID_discharge, gain)
print("Ok")

# 4) Set FEB CIS DACs
print(f"Setting FEB CIS DACs to {DACcharge}... ", end="")
for md in range(firstMD, firstMD + nMD):
    for feb_id in range(nchanperMD):
        feb.set_CIS_DAC(md, 0, feb_id, DACcharge)
print("Ok")

# 5) Loop on CIS events

step_x = [int(i) for i in range(nsamp)]

for event in range(n_events):
    # Send L1A trigger
    feb.send_L1A(bcid_l1a, 3)
    for md in range(firstMD, firstMD + nMD):
        for adc in range(nchanperMD):
            # Read ADC pipeline data
            hg_data = ppr.get_data_HG(md, adc, nsamp)
            lg_data = ppr.get_data_LG(md, adc, nsamp)

            all_hg_data[md * nchanperMD + adc].extend(hg_data)
            all_lg_data[md * nchanperMD + adc].extend(lg_data)

            # print(f"MD{md} ADC{adc} HG data={hg_data} LG data={lg_data}")

# ------------------ ASCII PLOTS -------------------
# print(all_hg_data)

ascii_plot_grid(0, step_x, all_hg_data, all_lg_data, nchanperMD=nchanperMD, ncols=6, nrows=2, width=20, height=20)
print("\nPulse Analysis Results")
print("=" * 80)
print(f"{'MD':<6}{'Ch':<6}{'HG_Ped':<10}{'HG_Peak':<10}{'HG_PeakIdx':<10}{'HG_Center':<12}{'HG_FWHM':<8}{'LG_Ped':<10}{'LG_Peak':<10}{'LG_PeakIdx':<10}{'LG_Center':<12}{'LG_FWHM':<8}")
print("-" * 80)

for md in range(firstMD, firstMD + nMD):
    for adc in range(nchanperMD):

        idx = md * nchanperMD + adc

        hg_pedestal, hg_peak, hg_peak_idx, hg_center, hg_width = analyze_pulse(all_hg_data[idx])
        lg_pedestal, lg_peak, lg_peak_idx, lg_center, lg_width = analyze_pulse(all_lg_data[idx])

        print(f"{md:<6}{adc:<6}{hg_pedestal:<10}{hg_peak:<10}{hg_peak_idx:<10}{hg_center:<12.2f}{hg_width:<8}{lg_pedestal:<10}{lg_peak:<10}{lg_peak_idx:<10}{lg_center:<12.2f}{lg_width:<8}")


for i in range(firstMD, firstMD + nMD):
    a = ppr.get_CRC_tot_errors(i, side="A")
    b = ppr.get_CRC_tot_errors(i, side="B")

    final_crc_sideA.append(a)
    final_crc_sideB.append(b)

print("\nFinal CRC Counters")
print("=" * 40)
print(f"{'MD':<6}{'A_init':<12}{'A_final':<12}{'ΔA':<12}"
      f"{'B_init':<12}{'B_final':<12}{'ΔB':<12}")

for idx, i in enumerate(range(firstMD, firstMD + nMD)):
    a0 = initial_crc_sideA[idx]
    b0 = initial_crc_sideB[idx]
    a1 = final_crc_sideA[idx]
    b1 = final_crc_sideB[idx]

    da = a1 - a0
    db = b1 - b0

    print(f"{f'MD{i}':<6}"
          f"{a0:<12}{a1:<12}{da:<12}"
          f"{b0:<12}{b1:<12}{db:<12}")


last_L1ID = ppr.read(PPrReg.LAST_EVT_L1ID)
last_BCID = ppr.read(PPrReg.LAST_EVT_BCID)
print(f"\nLast L1ID={last_L1ID}, BCID={last_BCID}")
print("\nCIS test finished successfully.")
