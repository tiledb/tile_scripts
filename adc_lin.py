#!/usr/bin/env python3
import time
import os
import Herakles
from array import array
from db_ppr_ipbus import PPr, FEB, PPrReg

import plotext as tplt
from math import ceil


# ------------------ PLOTTING -------------------

def ascii_plot_md(md, avgHG, avgLG, nchanperMD=12):
    for ch in range(nchanperMD):
        idx = ch + md * nchanperMD
        tplt.clear_figure()
        tplt.plot(range(len(avgHG[idx])), list(avgHG[idx]), label=f"HG Ch{ch}")
        tplt.plot(range(len(avgLG[idx])), list(avgLG[idx]), label=f"LG Ch{ch}")
        tplt.title(f"MD{md} Ch{ch}")
        tplt.show()

def ascii_plot_grid(md, step_x, avgHG, avgLG, nchanperMD=12, ncols=6, nrows=2, width=20, height=20):
    """
    Arrange ASCII plots for MD channels in a grid with fixed subplot size.
    """
    plots = []

    # Create fixed-size ASCII plots
    for ch in range(nchanperMD):
        idx = ch + md * nchanperMD
        tplt.clear_figure()
        tplt.plot(list(step_x), list(avgHG[idx]), label="")
        # print(f"Plotting Ch{ch} with step_x={list(step_x)} and avgHG={list(avgHG[idx])}")
        tplt.plot(list(step_x), list(avgLG[idx]), label="")
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


# linearFit
def linear_fit(x, y):
    """
    Returns slope, intercept, R2, max deviation
    """
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    # slope
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den = sum((x[i] - mean_x) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0

    # intercept
    intercept = mean_y - slope * mean_x

    # predictions
    y_fit = [slope * xi + intercept for xi in x]

    # R^2
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    ss_res = sum((y[i] - y_fit[i]) ** 2 for i in range(n))
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    # max deviation
    max_dev = max(abs(y[i] - y_fit[i]) for i in range(n))

    return slope, intercept, r2, max_dev



# ------------------ CONFIG ------------------

bcid_l1a = 500
HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

verbose = True
nsamp = 16
nchanperMD = 12
dbside = 0
nMD = 4
firstMD = 0
nsteps = 10
step_events = 1

# Scan parameters
scan_units = "ADC counts"  # "DACs bias offsets" or "ADC counts"
min_DAC = 1278# 1650 #1278
max_DAC = 2261# 2300 #2261

step_length_DAC = (max_DAC - min_DAC) / nsteps
step_length_ADC = (4096-0) / nsteps  # if using ADC counts

# ------------------ INITIALIZATION -------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = Herakles.Uhal(f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001")
ppr = PPr(ipbus)
feb = FEB(ppr)


print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")

# Allocate arrays for averaging
step_x = []  # injected value per step (ADCped)

avgHG = [[] for _ in range(nchanperMD * nMD)]
avgLG = [[] for _ in range(nchanperMD * nMD)]


# ------------------ CONFIG PHASE -------------------

print("Setting TTC internal... ", end="")
ret = ppr.set_global_TTC_internal()
print("Ok" if ret else "Failed")

print("Resetting CRC counters... ", end="")
ret = ppr.reset_integrator_fifo()  # or implement reset_CRC_counters()
print("Ok" if ret else "Failed")

print("Setting PPr enable deadtime bit in Global Trigger Conf...")
ret = ppr.set_global_trigger_deadtime(0)
print(f"  set bit to 0: {'Ok' if ret else 'Fail'}")
ret = ppr.set_global_trigger_deadtime(1)
print(f"  set bit to 1: {'Ok' if ret else 'Fail'}")

# ------------------ MAIN SCAN -------------------


print("==> Starting ADC linearity scan...")

for md in range(firstMD, firstMD + nMD):
    VinDACs = feb.convert_ped_ADC_to_DACs(0)
    DACbiasP, DACbiasN = VinDACs
    for feb_id in range(nchanperMD):
        feb.set_ped_HG_pos(md, dbside, feb_id, DACbiasP)
        feb.set_ped_HG_neg(md, dbside, feb_id, DACbiasN)
        feb.set_ped_LG_pos(md, dbside, feb_id, DACbiasP)
        feb.set_ped_LG_neg(md, dbside, feb_id, DACbiasN)
        
        feb.load_ped_HG(md, dbside, feb_id)
        feb.load_ped_LG(md, dbside, feb_id)
feb.send_L1A(bcid_l1a, 3)
last_L1ID = ppr.read(PPrReg.LAST_EVT_L1ID)
last_BCID = ppr.read(PPrReg.LAST_EVT_BCID)
time.sleep(0.1)  # small delay to ensure settings are applied

for step in range(nsteps):
    # ---- Compute DAC / ADC values per step ----
    if scan_units == "DACs bias offsets":
        DACbiasP = int(min_DAC + step * step_length_DAC)
        DACbiasN = int(max_DAC - step * step_length_DAC)
        ADCped = feb.convert_ped_DACs_to_ADC(DACbiasP, DACbiasN)
        # print(f"Step {step}: DAC Vp={DACbiasP}, DAC Vn={DACbiasN}, ADC counts={ADCped}")
    elif scan_units == "ADC counts":
        ADCped = int(step * step_length_ADC)
        VinDACs = feb.convert_ped_ADC_to_DACs(ADCped)
        DACbiasP, DACbiasN = VinDACs
        # print(f"Step {step}: ADC counts={ADCped}, DAC Vp={DACbiasP}, DAC Vn={DACbiasN}")

    step_x.append(ADCped)



    # ---- Configure FEBs ----
    # print("Setting FEB ADC bias offsets...")
    for md in range(firstMD, firstMD + nMD):
        for feb_id in range(nchanperMD):
            # print(f"  MD{md} FEB{feb_id}: Setting DACbiasP={DACbiasP}, DACbiasN={DACbiasN}")
            feb.set_ped_HG_pos(md, dbside, feb_id, DACbiasP)
            feb.set_ped_HG_neg(md, dbside, feb_id, DACbiasN)
            feb.set_ped_LG_pos(md, dbside, feb_id, DACbiasP)
            feb.set_ped_LG_neg(md, dbside, feb_id, DACbiasN)
            
            feb.load_ped_HG(md, dbside, feb_id)
            feb.load_ped_LG(md, dbside, feb_id)
            
        # ---- Loop over events per step ----
        time.sleep(0.01)  # small delay to ensure settings are applied
        for event in range(step_events):
            # Reads last Event BCID (disables busy to read pipelines).
            # LastEvtBCID = ppr.get_counter_last_event_BCID()

            # Reads last Event L1ID (disables busy to read pipelines).
            # LastEvtL1ID = ppr.get_counter_last_event_L1ID()
            # print(f"  Step {step} Event {event}: Sent L1A with BCID={bcid_l1a}, LastEvtBCID={LastEvtBCID}")

            # Send L1A trigger
            feb.send_L1A(bcid_l1a, 3)

            # Read pipeline data for selected MDs
            for adc in range(nchanperMD):
                hg_data = ppr.get_data_HG(md, adc, nsamp)
                lg_data = ppr.get_data_LG(md, adc, nsamp)

                hg_mean = sum(hg_data) / len(hg_data)
                lg_mean = sum(lg_data) / len(lg_data)
                # print(f"  Step {step} Event {event}: MD{md} ADC{adc} HG data={hg_data} LG data={lg_data}")
                
                avgHG[md * nchanperMD + adc].append(hg_mean)
                avgLG[md * nchanperMD + adc].append(lg_mean)
                # print(f"  Step {step} Event {event}: MD{md} ADC{adc} HG mean={hg_mean:.2f} LG mean={lg_mean:.2f}")
                # time.sleep(1)  # small delay for readability
                
                # print(f"  Step {step} Event {event}: MD{md} ADC{adc} HG={hg_data} LG={lg_data}")
                # print(f"  Step {step} Event {event}: MD{md} ADC{adc} HG avg={sum(hg_data)/len(hg_data):.2f} LG avg={sum(lg_data)/len(lg_data):.2f}")
                # print(f"  Step {step} Event {event}: MD{md} ADC{adc} ADCped {ADCped} HG mean={hg_mean:.2f} LG mean={lg_mean:.2f}")

            # Print last event IDs for monitoring
            last_L1ID = ppr.read(PPrReg.LAST_EVT_L1ID)
            last_BCID = ppr.read(PPrReg.LAST_EVT_BCID)
            # print(f"Step {step} done. Last L1ID={last_L1ID}, BCID={last_BCID}")




# Optional ASCII terminal plots
#ascii_plot_md(0, avgHG, avgLG)
  

print("\n========== LINEAR FIT RESULTS ==========\n")

for md in range(nMD):
    ascii_plot_grid(md, step_x, avgHG, avgLG, nchanperMD=nchanperMD, ncols=6, nrows=2, width=20, height=20)
    
    for ch in range(nchanperMD):
        idx = md * nchanperMD + ch

        # ---- HG fit ----
        slope_hg, offset_hg, r2_hg, maxdev_hg = linear_fit(step_x, avgHG[idx])

        # ---- LG fit ----
        slope_lg, offset_lg, r2_lg, maxdev_lg = linear_fit(step_x, avgLG[idx])

        print(f"MD{md} Ch{ch}")
        print(f"  HG: slope={slope_hg:.6f}, offset={offset_hg:.3f}, "
              f"R2={r2_hg:.6f}, max_dev={maxdev_hg:.3f}")
        print(f"  LG: slope={slope_lg:.6f}, offset={offset_lg:.3f}, "
              f"R2={r2_lg:.6f}, max_dev={maxdev_lg:.3f}")
        print()


print("\nADC linearity scan finished successfully.")
