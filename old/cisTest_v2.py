#!/usr/bin/env python3
import time
import Herakles
import math
import numpy as np
import plotext as tplt
from db_ppr_ipbus import PPr, FEB, PPrReg

# -----Scientific functions-----

def analyze_pulse(samples, pedestal_samples=4, noise_sigma_threshold=5, threshold_fraction=0.5):
    if not samples or len(samples) < pedestal_samples + 2:
        return 0, 0, 0, 0, 0

    pedestal_region = samples[:pedestal_samples]
    pedestal = sum(pedestal_region) / pedestal_samples

    variance = sum((x - pedestal) ** 2 for x in pedestal_region) / pedestal_samples
    noise_sigma = math.sqrt(variance)

    signal = [x - pedestal for x in samples]

    peak_value = max(signal)
    peak_index = signal.index(peak_value)

    if noise_sigma == 0 or peak_value < noise_sigma_threshold * noise_sigma:
        return pedestal, 0, 0, 0, 0

    total = sum(signal)
    center_of_mass = sum(i * v for i, v in enumerate(signal)) / total if total > 0 else 0

    half_max = peak_value * threshold_fraction
    above_half = [i for i, v in enumerate(signal) if v >= half_max]
    fwhm = above_half[-1] - above_half[0] if len(above_half) >= 2 else 0

    return pedestal, peak_value, peak_index, center_of_mass, fwhm

# ------------------ ASCII GRID PLOTS -------------------

def ascii_plot_grid(md, step_x, hg_data_events, lg_data_events, nchanperMD=12, ncols=6, nrows=2, width=25, height=12):
    """
    Arrange ASCII plots for MD channels in a grid with fixed subplot size.
    hg_data_events, lg_data_events: list of event arrays
    """
    plots = []

    # Take first event for plotting
    hg_data = hg_data_events[0]
    lg_data = lg_data_events[0]

    for ch in range(nchanperMD):
        tplt.clear_figure()
        tplt.plotsize(width, height)
        tplt.plot(list(step_x), list(hg_data[ch]), label="", color="red")
        tplt.plot(list(step_x), list(lg_data[ch]), label="", color="blue")
        tplt.title(f"Ch{ch}")
        plot_str = tplt.build()
        plots.append(plot_str.splitlines())

    # Pad plots
    for i in range(len(plots)):
        while len(plots[i]) < height:
            plots[i].append(" " * width)

    # Print grid
    for row_idx in range(nrows):
        row_plots = plots[row_idx*ncols:(row_idx+1)*ncols]
        for line_idx in range(height):
            print("  ".join(p[line_idx] for p in row_plots))
        print("\n")



def plot_md_variables(md, nchanperMD, all_hg_peaks, all_lg_peaks,
                           all_hg_centers, all_lg_centers,
                           all_hg_fwhm, all_lg_fwhm,
                           all_hg_pedestal, all_lg_pedestal,
                           width=25, height=12):
    """
    Display 4 variable plots per MD horizontally in ASCII.
    Each variable gets a fixed-size mini-plot, HG=red, LG=blue.
    """

    channels = list(range(nchanperMD))

    # Extract first event per variable
    hg_peaks = all_hg_peaks[0][md*nchanperMD:(md+1)*nchanperMD]
    lg_peaks = all_lg_peaks[0][md*nchanperMD:(md+1)*nchanperMD]

    hg_centers = all_hg_centers[0][md*nchanperMD:(md+1)*nchanperMD]
    lg_centers = all_lg_centers[0][md*nchanperMD:(md+1)*nchanperMD]

    hg_fwhm = all_hg_fwhm[0][md*nchanperMD:(md+1)*nchanperMD]
    lg_fwhm = all_lg_fwhm[0][md*nchanperMD:(md+1)*nchanperMD]

    hg_ped = all_hg_pedestal[0][md*nchanperMD:(md+1)*nchanperMD]
    lg_ped = all_lg_pedestal[0][md*nchanperMD:(md+1)*nchanperMD]

    variables = [
        ("Peaks", hg_peaks, lg_peaks),
        ("Centers", hg_centers, lg_centers),
        ("FWHM", hg_fwhm, lg_fwhm),
        ("Pedestal", hg_ped, lg_ped)
    ]

    # Build ASCII plots as strings
    ascii_plots = []
    for title, hg, lg in variables:
        tplt.clear_figure()
        tplt.plotsize(width, height)
        # Y-limits padded
        y_min = min(min(hg), min(lg))
        y_max = max(max(hg), max(lg))
        if y_min == y_max:
            y_min -= 1
            y_max += 1
        tplt.ylim(y_min*0.9, y_max*1.1)
        tplt.plot(channels, hg, marker="dot", color="red")
        tplt.plot(channels, lg, marker="dot", color="blue")
        tplt.title(title)
        # Capture ASCII as list of lines
        ascii_str = tplt.build().splitlines()
        # Ensure fixed height
        while len(ascii_str) < height:
            ascii_str.insert(0, " " * width)
        ascii_plots.append(ascii_str)

    # Print the 4 plots side by side
    for line_idx in range(height):
        line = "  ".join(plot[line_idx] for plot in ascii_plots)
        print(line)

    # Print x-axis labels below
    x_labels = "  ".join("".join(f"{c:>2}" for c in channels) for _ in ascii_plots)
    print("\n" + x_labels)
        
        
        
# ------------------ STATISTICS -------------------

def avg_std(data):
    arr = np.array(data)
    return np.mean(arr), np.std(arr)

# ------------------ READ MD DATA -------------------

def read_md_data(md, nsamp, nchanperMD, bcid_l1a):
    """
    Reads all channels of an MD.
    Returns: hg_data_md, lg_data_md, hg_peak_md, lg_peak_md,
             hg_center_md, lg_center_md, hg_fwhm_md, lg_fwhm_md,
             hg_pedestal_md, lg_pedestal_md
    """
    hg_data_md = []
    lg_data_md = []
    hg_peak_md = []
    lg_peak_md = []
    hg_center_md = []
    lg_center_md = []
    hg_fwhm_md = []
    lg_fwhm_md = []
    hg_pedestal_md = []
    lg_pedestal_md = []

    # Send L1A before readout
    feb.send_L1A(bcid_l1a, 3)
    time.sleep(0.05)

    for adc in range(nchanperMD):
        hg_data = ppr.get_data_HG(md, adc, nsamp)
        lg_data = ppr.get_data_LG(md, adc, nsamp)

        hg_ped, hg_peak, hg_idx, hg_center, hg_width = analyze_pulse(hg_data)
        lg_ped, lg_peak, lg_idx, lg_center, lg_width = analyze_pulse(lg_data)

        hg_data_md.append(hg_data)
        lg_data_md.append(lg_data)
        hg_peak_md.append(hg_peak)
        lg_peak_md.append(lg_peak)
        hg_center_md.append(hg_center)
        lg_center_md.append(lg_center)
        hg_fwhm_md.append(hg_width)
        lg_fwhm_md.append(lg_width)
        hg_pedestal_md.append(hg_ped)
        lg_pedestal_md.append(lg_ped)

    return (
        hg_data_md, lg_data_md, hg_peak_md, lg_peak_md,
        hg_center_md, lg_center_md, hg_fwhm_md, lg_fwhm_md,
        hg_pedestal_md, lg_pedestal_md
    )

# ------------------ CONFIG ------------------

HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

# ------------------ INITIALIZATION -------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = Herakles.Uhal(f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001")
ppr = PPr(ipbus)
feb = FEB(ppr)
print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")

nsamp = 16
nchanperMD = 12
nMD = 2
firstMD = 0
dbside = 0

# ------------------ CIS READOUT -------------------

def cis_readout(ppr, feb, gain=0, DACcharge=2000, nsamp=16, nchanperMD=12, nMD=2, firstMD=0, dbside=0):
    n_events = 1
    bcid_l1a = 2246
    BCID_charge = 500
    BCID_discharge = 2200
    ADCped = 100

    max_DAC_charge = 4095
    min_DAC_charge = 0

    # Output arrays
    all_hg_data = []
    all_lg_data = []
    all_hg_peaks = []
    all_lg_peaks = []
    all_hg_centers = []
    all_lg_centers = []
    all_hg_fwhm = []
    all_lg_fwhm = []
    all_hg_pedestal = []
    all_lg_pedestal = []

    # CONFIG PHASE
    ppr.set_global_TTC_internal()
    DACbiasP, DACbiasN = feb.convert_ped_ADC_to_DACs(ADCped)

    for md in range(firstMD, firstMD + nMD):
        for feb_id in range(nchanperMD):
            feb.set_ped_HG_pos(md, dbside, feb_id, DACbiasP)
            feb.set_ped_HG_neg(md, dbside, feb_id, DACbiasN)
            feb.set_ped_LG_pos(md, dbside, feb_id, DACbiasP)
            feb.set_ped_LG_neg(md, dbside, feb_id, DACbiasN)
            feb.load_ped_HG(md, dbside, feb_id)
            feb.load_ped_LG(md, dbside, feb_id)

    for md in range(firstMD, firstMD + nMD):
        for adc in range(nchanperMD):
            feb.set_switches_noise(md, dbside, feb=adc)
        feb.set_CIS_BCID_settings(md, dbside, BCID_charge, BCID_discharge, gain)

    # DACcharge SWEEP
    print("\n==> Starting DACcharge sweep")
    for md in range(firstMD, firstMD + nMD):
        for feb_id in range(nchanperMD):
            feb.set_CIS_DAC(md, dbside, feb_id, DACcharge)
    time.sleep(0.05)

    # EVENTS
    for event in range(n_events):
        hg_data_event = []
        lg_data_event = []
        hg_peak_event = []
        lg_peak_event = []
        hg_center_event = []
        lg_center_event = []
        hg_fwhm_event = []
        lg_fwhm_event = []
        hg_ped_event = []
        lg_ped_event = []

        for md in range(firstMD, firstMD + nMD):
            hg_data_md, lg_data_md, hg_peak_md, lg_peak_md, hg_center_md, lg_center_md, \
            hg_fwhm_md, lg_fwhm_md, hg_pedestal_md, lg_pedestal_md = \
                read_md_data(md, nsamp, nchanperMD, bcid_l1a)

            # append per MD
            hg_data_event.extend(hg_data_md)
            lg_data_event.extend(lg_data_md)
            hg_peak_event.extend(hg_peak_md)
            lg_peak_event.extend(lg_peak_md)
            hg_center_event.extend(hg_center_md)
            lg_center_event.extend(lg_center_md)
            hg_fwhm_event.extend(hg_fwhm_md)
            lg_fwhm_event.extend(lg_fwhm_md)
            hg_ped_event.extend(hg_pedestal_md)
            lg_ped_event.extend(lg_pedestal_md)

        # append per event
        all_hg_data.append(hg_data_event)
        all_lg_data.append(lg_data_event)
        all_hg_peaks.append(hg_peak_event)
        all_lg_peaks.append(lg_peak_event)
        all_hg_centers.append(hg_center_event)
        all_lg_centers.append(lg_center_event)
        all_hg_fwhm.append(hg_fwhm_event)
        all_lg_fwhm.append(lg_fwhm_event)
        all_hg_pedestal.append(hg_ped_event)
        all_lg_pedestal.append(lg_ped_event)

    return all_hg_data, all_lg_data, all_hg_peaks, all_lg_peaks, \
           all_hg_centers, all_lg_centers, all_hg_fwhm, all_lg_fwhm, \
           all_hg_pedestal, all_lg_pedestal

# ------------------ RUN CIS READOUT -------------------

all_hg_data, all_lg_data, all_hg_peaks, all_lg_peaks, \
all_hg_centers, all_lg_centers, all_hg_fwhm, all_lg_fwhm, \
all_hg_pedestal, all_lg_pedestal = cis_readout(
    ppr, feb, gain=1, DACcharge=2000, nsamp=nsamp,
    nchanperMD=nchanperMD, nMD=nMD, firstMD=firstMD, dbside=dbside
)

# ------------------ PLOT + SUMMARY -------------------

step_x = np.arange(nsamp)

for md in range(firstMD, firstMD + nMD):
    print(f"\n\n==> MD{md} ASCII Plots")
    ascii_plot_grid(md, step_x, all_hg_data, all_lg_data,
                    nchanperMD=nchanperMD, ncols=6, nrows=2, width=25, height=12)


    print(f"\n\n==> MD{md} Variable Plots")
    plot_md_variables(md, nchanperMD, all_hg_peaks, all_lg_peaks,
                    all_hg_centers, all_lg_centers,
                    all_hg_fwhm, all_lg_fwhm,
                    all_hg_pedestal, all_lg_pedestal)