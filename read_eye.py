#!/usr/bin/env python3
import sys
import time
import numpy as np
import datetime
from db_ppr_ipbus import PPr, PPrReg, DBReg


# ---------------------------
# Grid plotting helpers
# ---------------------------
from itertools import groupby
from scipy.special import erfc


# ---------------------------
# Logging helper
# ---------------------------
def log(msg, verbose):
    if verbose:
        print(f"[{datetime.datetime.now()}] {msg}", flush=True)

# ---------------------------
# Main eye acquisition
# ---------------------------
def eye_func(ppr, verbose=False):
    """
    Acquire eye diagrams using the PPr object
    """
    log("Reading eye diagrams...", verbose)
    eye = ppr.read_eye(verbose=verbose)
    log("Eye diagrams acquired", verbose)
    return np.array(eye)  # convert to NumPy array for plotting

# ---------------------------
# Terminal plot
# ---------------------------
def plot_eye_terminal(eye, lane=0, width=80, height=25):
    print(f"\nRendering lane {lane}...\n")
    data = eye[lane]
    v, h = data.shape

    v_step = max(1, v // height)
    h_step = max(1, h // width)

    chars = " .:*#@"
    max_val = np.max(data) or 1

    for vv in range(0, v, v_step):
        line = ""
        for hh in range(0, h, h_step):
            val = data[vv][hh] / max_val
            idx = int(val * (len(chars) - 1))
            line += chars[idx]
        print(line)

# ---------------------------
# Plotext heatmap
# ---------------------------
def plot_eye_heatmap(eye, lane=0, width=100, height=30):
    print(f"\nHeatmap lane {lane}\n")
    data = eye[lane]
    v, h = data.shape
    v_step = max(1, v // height)
    h_step = max(1, h // width)
    shades = " .:-=+*#%@"
    max_val = data.max() or 1

    for vv in range(0, v, v_step):
        line = ""
        for hh in range(0, h, h_step):
            val = data[vv][hh] / max_val
            idx = int(val * (len(shades) - 1))
            line += shades[idx] * 2
        print(line)


# Corrected and robust metrics computation
# ---------------------------
def compute_metrics(data, threshold=1e-6):
    """
    Compute comprehensive eye diagram metrics with proper handling
    of all-zero or bad data. Returns worst-case values if eye is flat.
    """
    # Handle all-zero data
    if np.all(data == 0):
        return {
            'open_area': 0.0,          # 0% open
            'max_h_open': 0,           # no horizontal opening
            'max_v_open': 0,           # no vertical opening
            'eye_height': 0.0,         # no swing
            'rms_jitter': 0.0,         # no crossings
            'peak_to_peak_jitter': 0.0,
            'q_factor': 0.0,
            'snr': 0.0,
            'crossing_point': 0.5,     # neutral
            'ber': 1.0                 # worst case
        }

    v, h = data.shape
    max_val = data.max()
    min_val = data.min()
    thr = threshold if threshold > 0 else max_val * 0.01

    # ---------------------------
    # Eye open area
    # ---------------------------
    mask = data >= thr  # points above threshold are considered open
    open_area = np.sum(mask) / (v * h)

    # Horizontal max open
    max_h_open = max(
        (sum(1 for _ in g) for row in mask for k, g in groupby(row) if k),
        default=0
    )
    # Vertical max open
    max_v_open = max(
        (sum(1 for _ in g) for col in mask.T for k, g in groupby(col) if k),
        default=0
    )

    # Eye amplitude / height
    eye_height = max_val - min_val

    # ---------------------------
    # Crossing point & jitter
    # ---------------------------
    mid_val = (max_val + min_val) / 2
    crossing_positions = []
    for row in data:
        for i in range(1, len(row)):
            if (row[i-1] < mid_val <= row[i]) or (row[i-1] >= mid_val > row[i]):
                crossing_positions.append(i)
    if crossing_positions:
        rms_jitter = np.std(crossing_positions)
        peak_to_peak_jitter = np.max(crossing_positions) - np.min(crossing_positions)
        crossing_point = np.mean(crossing_positions) / h
    else:
        rms_jitter = 0.0
        peak_to_peak_jitter = 0.0
        crossing_point = 0.5

    # ---------------------------
    # Q-factor & SNR
    # ---------------------------
    ones = data > mid_val
    zeros = data <= mid_val
    mu1, sigma1 = (data[ones].mean(), data[ones].std()) if np.any(ones) else (0, 1)
    mu0, sigma0 = (data[zeros].mean(), data[zeros].std()) if np.any(zeros) else (0, 1)
    q_factor = (mu1 - mu0) / (sigma1 + sigma0) if (sigma1 + sigma0) > 0 else 0
    snr = eye_height / (np.std(data) or 1)
    ber_estimate = 0.5 * erfc(q_factor / np.sqrt(2)) if q_factor > 0 else 1.0

    return {
        'open_area': open_area,
        'max_h_open': max_h_open,
        'max_v_open': max_v_open,
        'eye_height': eye_height,
        'rms_jitter': rms_jitter,
        'peak_to_peak_jitter': peak_to_peak_jitter,
        'q_factor': q_factor,
        'snr': snr,
        'crossing_point': crossing_point,
        'ber': ber_estimate
    }


# ---------------------------
# 4x4 grid plotting with metrics on top
# ---------------------------
def plot_eye_grid_terminal(eye, width=25, height=10, threshold=1e-6):
    """
    Plot multiple eye diagrams in a 4x4 grid with a column of metrics on top of each lane.
    Each metric is printed on its own line above the mini eye diagram.
    """
    lanes_per_row = 4
    #num_lanes = len(eye)
    num_lanes = 4
    
    for row in range((num_lanes + lanes_per_row - 1) // lanes_per_row):
        # First, gather metrics for all lanes in this row
        lane_metrics = []
        lane_lines_list = []
        max_eye_lines = 0

        for col in range(lanes_per_row):
            lane = row * lanes_per_row + col
            if lane >= num_lanes:
                break

            data = eye[lane]
            v, h = data.shape
            v_step = max(1, v // height)
            h_step = max(1, h // width)
            max_val = data.max() or 1

            metrics = compute_metrics(data, threshold)
            # Build metrics lines
            metrics_lines = [
                f"L{lane:02d}",
                f"Open Area : {metrics['open_area']*100:5.1f}%",
                f"Max H     : {metrics['max_h_open']}",
                f"Max V     : {metrics['max_v_open']}",
                f"Eye H     : {metrics['eye_height']:.2f}",
                f"RMS J     : {metrics['rms_jitter']:.2f}",
                f"P2P J     : {metrics['peak_to_peak_jitter']:.2f}",
                f"Q-factor  : {metrics['q_factor']:.2f}",
                f"SNR       : {metrics['snr']:.2f}",
                f"Cross Pt  : {metrics['crossing_point']:.2f}",
                f"BER       : {metrics['ber']:.1e}"
            ]
            lane_metrics.append(metrics_lines)

            # Build mini eye diagram lines
            eye_lines = []
            for vv in range(0, v, v_step):
                line = ""
                for hh in range(0, h, h_step):
                    val = data[vv][hh] / max_val
                    color = int(16 + val * 200)
                    line += f"\033[48;5;{color}m \033[0m"
                eye_lines.append(line)
            lane_lines_list.append(eye_lines)
            max_eye_lines = max(max_eye_lines, len(eye_lines))

        # Print metrics lines first, lane by lane
        num_metric_lines = max(len(m) for m in lane_metrics)
        for i in range(num_metric_lines):
            line = ""
            for metrics_lines in lane_metrics:
                if i < len(metrics_lines):
                    line += f"{metrics_lines[i]:<{width}}  "
                else:
                    line += " " * width + "  "
            print(line)

        # Print eye diagram lines
        for i in range(max_eye_lines):
            line = ""
            for eye_lines in lane_lines_list:
                if i < len(eye_lines):
                    line += f"{eye_lines[i]:<{width}}  "
                else:
                    line += " " * width + "  "
            print(line)

        print("\n")

# ---------------------------
# Main
# ---------------------------

# -------------------------------
# Connection
# -------------------------------
from db_ppr_ipbus import *
HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.3"

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = IPbus(HostIPaddressServer, PPrIPaddressServer)
ppr = PPr(ipbus.ipbus)
# feb = FEB(ppr)  # create FEB instance

if __name__ == "__main__":
    verbose = "--debug" in sys.argv

    log("===== START =====", verbose)

    try:

        eye = eye_func(ppr, verbose=verbose)

        plot_eye_grid_terminal(eye)

    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        raise

    log("===== END =====", verbose)