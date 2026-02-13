#!/usr/bin/env python3
import time
import os
import Herakles
from array import array
from db_ppr_ipbus import PPr, FEB, PPrReg

import plotext as tplt
import math
import numpy as np  # still needed for averaging stats

# -----Scientific functions-----

def analyze_pulse(samples,
                  pedestal_samples=4,
                  noise_sigma_threshold=5,
                  threshold_fraction=0.5):

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

def ascii_plot_grid(step_x, all_hg_peaks, all_lg_peaks, nchanperMD=12, ncols=6, nrows=2, width=20, height=10):
    plots = []
    for ch in range(nchanperMD):
        tplt.clear_figure()
        hg_y = [all_hg_peaks[s][ch] for s in range(len(all_hg_peaks))]
        lg_y = [all_lg_peaks[s][ch] for s in range(len(all_lg_peaks))]

        tplt.plot(step_x, hg_y, label="", color="red")
        tplt.plot(step_x, lg_y, label="", color="green")
        tplt.title(f"Ch{ch}")
        tplt.plotsize(width, height)
        plot_str = tplt.build()
        plots.append(plot_str.splitlines())

    for i in range(len(plots)):
        while len(plots[i]) < height:
            plots[i].append(" " * width)

    for row_idx in range(nrows):
        row_plots = plots[row_idx*ncols : (row_idx+1)*ncols]
        for line_idx in range(height):
            print("  ".join(p[line_idx] for p in row_plots))
        print("\n")


# ------------------ LINEAR FIT FUNCTION -------------------

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


# ------------------ STATISTICS -------------------

def avg_std(data):
    arr = np.array(data)
    return np.mean(arr), np.std(arr)

def report_stats(name, data, nchanperMD):
    print(f"\n-- {name} --")
    for ch in range(nchanperMD):
        mean, std = avg_std(data[:, ch])
        print(f"Ch{ch}: mean={mean:.3f}, std={std:.3f}")


# ------------------ MD READ WITH RETRY -------------------

def read_md_data_with_retry(md, nsamp, nchanperMD, bcid_l1a,
                            previous_hg_peaks=None, previous_lg_peaks=None,
                            threshold=0.9, max_retries=3):

    ppr_read = ppr.read
    get_HG   = ppr.get_data_HG
    get_LG   = ppr.get_data_LG
    send_L1A = feb.send_L1A

    retry = 0
    while retry <= max_retries:

        hg_peaks_step     = [0.0] * nchanperMD
        lg_peaks_step     = [0.0] * nchanperMD
        hg_centers_step   = [0.0] * nchanperMD
        lg_centers_step   = [0.0] * nchanperMD
        hg_fwhm_step      = [0.0] * nchanperMD
        lg_fwhm_step      = [0.0] * nchanperMD
        hg_pedestal_step  = [0.0] * nchanperMD
        lg_pedestal_step  = [0.0] * nchanperMD

        send_L1A(bcid_l1a, 3)
        time.sleep(0.05)

        for adc in range(nchanperMD):
            hg_data = get_HG(md, adc, nsamp)
            lg_data = get_LG(md, adc, nsamp)

            hg_ped, hg_peak, _, hg_center, hg_width = analyze_pulse(hg_data)
            lg_ped, lg_peak, _, lg_center, lg_width = analyze_pulse(lg_data)

            hg_peaks_step[adc]     = hg_peak
            lg_peaks_step[adc]     = lg_peak
            hg_centers_step[adc]   = hg_center
            lg_centers_step[adc]   = lg_center
            hg_fwhm_step[adc]      = hg_width
            lg_fwhm_step[adc]      = lg_width
            hg_pedestal_step[adc]  = hg_ped
            lg_pedestal_step[adc]  = lg_ped

        # Keep mandatory hardware reads
        last_L1ID = ppr_read(PPrReg.LAST_EVT_L1ID)
        last_BCID = ppr_read(PPrReg.LAST_EVT_BCID)

        retry_needed = False
        if previous_hg_peaks is not None:
            for ch in range(nchanperMD):
                if (hg_peaks_step[ch] < previous_hg_peaks[ch] * threshold or
                    lg_peaks_step[ch] < previous_lg_peaks[ch] * threshold):
                    retry_needed = True
                    break

        if not retry_needed:
            return (hg_peaks_step, lg_peaks_step, hg_centers_step, lg_centers_step,
                    hg_fwhm_step, lg_fwhm_step, hg_pedestal_step, lg_pedestal_step)

        retry += 1
        print(f"MD{md} retry {retry}/{max_retries} due to low peak(s)...")
        time.sleep(0.05)

    print(f"MD{md} reached max retries ({max_retries}), returning last readout")
    return (hg_peaks_step, lg_peaks_step, hg_centers_step, lg_centers_step,
            hg_fwhm_step, lg_fwhm_step, hg_pedestal_step, lg_pedestal_step)


# ------------------ CONFIG ------------------

HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

nsamp = 16
nchanperMD = 12
nMD = 2
firstMD = 0
dbside = 0

n_events = 1

bcid_l1a = 2246
BCID_charge = 500
BCID_discharge = 2200
gain = 0

ADCped = 100

nsteps = 40
max_DAC_charge = 4095
min_DAC_charge = 0
step_length_DAC = (max_DAC_charge - min_DAC_charge) / (nsteps - 1)


# ------------------ INITIALIZATION -------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = Herakles.Uhal(f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001")
ppr = PPr(ipbus)
feb = FEB(ppr)
print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")


# ------------------ STORAGE -------------------

step_x = []

all_hg_peaks     = []
all_lg_peaks     = []
all_hg_centers   = []
all_lg_centers   = []
all_hg_fwhm      = []
all_lg_fwhm      = []
all_hg_pedestal  = []
all_lg_pedestal  = []


# ------------------ CONFIG PHASE -------------------

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

for md in range(firstMD, firstMD + nMD):
    feb.set_CIS_BCID_settings(md, dbside, BCID_charge, BCID_discharge, gain)


# ------------------ DACcharge SWEEP -------------------

print("\n==> Starting DACcharge sweep")

ppr_read = ppr.read
send_L1A = feb.send_L1A

for step in range(nsteps):

    DACcharge = int(min_DAC_charge + step * step_length_DAC)
    step_x.append(DACcharge)

    print(f"Step {step+1}/{nsteps}  DACcharge = {DACcharge}")

    for md in range(firstMD, firstMD + nMD):
        for feb_id in range(nchanperMD):
            feb.set_CIS_DAC(md, dbside, feb_id, DACcharge)

    time.sleep(0.05)

    hg_peaks_step     = []
    lg_peaks_step     = []
    hg_centers_step   = []
    lg_centers_step   = []
    hg_fwhm_step      = []
    lg_fwhm_step      = []
    hg_pedestal_step  = []
    lg_pedestal_step  = []

    for event in range(n_events):
        send_L1A(bcid_l1a, 3)
        time.sleep(0.05)

        for md in range(firstMD, firstMD + nMD):

            previous_hg = all_hg_peaks[-1][md*nchanperMD:(md+1)*nchanperMD] if step else None
            previous_lg = all_lg_peaks[-1][md*nchanperMD:(md+1)*nchanperMD] if step else None

            (hg_p, lg_p, hg_c, lg_c,
             hg_w, lg_w, hg_pd, lg_pd) = read_md_data_with_retry(
                md, nsamp, nchanperMD, bcid_l1a,
                previous_hg_peaks=previous_hg,
                previous_lg_peaks=previous_lg,
                threshold=0.9, max_retries=0
            )

            hg_peaks_step.extend(hg_p)
            lg_peaks_step.extend(lg_p)
            hg_centers_step.extend(hg_c)
            lg_centers_step.extend(lg_c)
            hg_fwhm_step.extend(hg_w)
            lg_fwhm_step.extend(lg_w)
            hg_pedestal_step.extend(hg_pd)
            lg_pedestal_step.extend(lg_pd)

        last_L1ID = ppr_read(PPrReg.LAST_EVT_L1ID)
        last_BCID = ppr_read(PPrReg.LAST_EVT_BCID)

    all_hg_peaks.append(hg_peaks_step)
    all_lg_peaks.append(lg_peaks_step)
    all_hg_centers.append(hg_centers_step)
    all_lg_centers.append(lg_centers_step)
    all_hg_fwhm.append(hg_fwhm_step)
    all_lg_fwhm.append(lg_fwhm_step)
    all_hg_pedestal.append(hg_pedestal_step)
    all_lg_pedestal.append(lg_pedestal_step)


# ------------------ ASCII LINEARITY PLOTS -------------------

for md in range(firstMD, firstMD + nMD):
    print(f"\n==> MD{md} Linearity")
    step_hg_peaks = [all_hg_peaks[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_peaks))]
    step_lg_peaks = [all_lg_peaks[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_peaks))]
    ascii_plot_grid(step_x, step_hg_peaks, step_lg_peaks, nchanperMD=nchanperMD, ncols=6, nrows=2, width=20, height=10) 
    print(f"\n==> MD{md} Centers")
    step_hg_centers = [all_hg_centers[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_centers))]
    step_lg_centers = [all_lg_centers[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_centers))]
    ascii_plot_grid(step_x, step_hg_centers, step_lg_centers, nchanperMD=nchanperMD, ncols=6, nrows=2, width=20, height=10) 
    print(f"\n==> MD{md} FWHM")
    step_hg_fwhm = [all_hg_fwhm[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_fwhm))]
    step_lg_fwhm = [all_lg_fwhm[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_fwhm))]
    ascii_plot_grid(step_x, step_hg_fwhm, step_lg_fwhm, nchanperMD=nchanperMD, ncols=6, nrows=2, width=20, height=10)
    print(f"\n==> MD{md} Pedestal")
    step_hg_pedestal = [all_hg_pedestal[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_pedestal))]
    step_lg_pedestal = [all_lg_pedestal[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_pedestal))]
    ascii_plot_grid(step_x, step_hg_pedestal, step_lg_pedestal, nchanperMD=nchanperMD, ncols=6, nrows=2, width=20, height=10)


# ------------------ LINEAR FIT AND STATISTICS -------------------
print("\n\n==> Compact Summary of linear fits and stats\n")

for md in range(firstMD, firstMD + nMD):
    print(f"\n==> MD{md} summary")

    step_hg_peaks = np.array([all_hg_peaks[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_peaks))])
    step_lg_peaks = np.array([all_lg_peaks[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_peaks))])
    
    step_hg_centers = np.array([all_hg_centers[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_centers))])
    step_lg_centers = np.array([all_lg_centers[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_centers))])
    
    step_hg_fwhm = np.array([all_hg_fwhm[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_fwhm))])
    step_lg_fwhm = np.array([all_lg_fwhm[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_fwhm))])
    
    step_hg_pedestal = np.array([all_hg_pedestal[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_hg_pedestal))])
    step_lg_pedestal = np.array([all_lg_pedestal[s][md * nchanperMD:(md + 1) * nchanperMD] for s in range(len(all_lg_pedestal))])

    # Print header
    header = f"{'Ch':>2} | {'HG slope':>8} {'HG int':>8} {'HG R2':>6} {'HG maxDev':>10} | {'LG slope':>8} {'LG int':>8} {'LG R2':>6} {'LG maxDev':>10} | HG center±std | LG center±std | HG FWHM±std | LG FWHM±std | HG ped±std | LG ped±std"
    print(header)
    print("-" * len(header))

    for ch in range(nchanperMD):
        # linear fit HG
        hg_slope, hg_intercept, hg_r2, hg_max_dev = linear_fit(step_x, step_hg_peaks[:, ch])
        # linear fit LG
        lg_slope, lg_intercept, lg_r2, lg_max_dev = linear_fit(step_x, step_lg_peaks[:, ch])
        # averages and stds
        hg_center_mean, hg_center_std = avg_std(step_hg_centers[:, ch])
        lg_center_mean, lg_center_std = avg_std(step_lg_centers[:, ch])
        hg_fwhm_mean, hg_fwhm_std = avg_std(step_hg_fwhm[:, ch])
        lg_fwhm_mean, lg_fwhm_std = avg_std(step_lg_fwhm[:, ch])
        hg_ped_mean, hg_ped_std = avg_std(step_hg_pedestal[:, ch])
        lg_ped_mean, lg_ped_std = avg_std(step_lg_pedestal[:, ch])

        print(f"{ch:>2} | {hg_slope:8.2f} {hg_intercept:8.2f} {hg_r2:6.3f} {hg_max_dev:10.2f} | "
              f"{lg_slope:8.2f} {lg_intercept:8.2f} {lg_r2:6.3f} {lg_max_dev:10.2f} | "
              f"{hg_center_mean:.2f}±{hg_center_std:.2f} | {lg_center_mean:.2f}±{lg_center_std:.2f} | "
              f"{hg_fwhm_mean:.2f}±{hg_fwhm_std:.2f} | {lg_fwhm_mean:.2f}±{lg_fwhm_std:.2f} | "
              f"{hg_ped_mean:.2f}±{hg_ped_std:.2f} | {lg_ped_mean:.2f}±{lg_ped_std:.2f}")
