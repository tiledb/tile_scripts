#!/usr/bin/env python3
import sys
import time
import numpy as np
import Herakles
import datetime

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
def eye_func(verbose=False):
    IPaddressServer = "localhost"

    class IPbus:
        def __init__(self, ipaddress, verbose=False):
            self.verbose = verbose

            log("Creating IPbus connection...", self.verbose)

            self.ipbus = Herakles.Uhal(
                "tcp://192.168.0.201:10203?target=192.168.0.3:50001"
            )

            log("Connection object created", self.verbose)

            self.ipbus.SetVerbose(verbose)
            log(f"Verbose set to {verbose}", self.verbose)

        def RODConfigWrite(self, add, val):
            log(f"[WRITE] addr=0x{add:X}, val=0x{val:X}", self.verbose)
            self.ipbus.Write(add, val)
            log("[WRITE DONE]", self.verbose)

        def ReadVal(self, add):
            log(f"[READ] addr=0x{add:X}", self.verbose)
            val = self.ipbus.Read(add, 1)
            log(f"[READ DONE] -> {val}", self.verbose)
            return val

    log("Initializing IPbus...", verbose)
    ipbus = IPbus(IPaddressServer, verbose)
    log("IPbus initialized", verbose)

    # ---------------------------
    # Registers
    # ---------------------------
    reg_control = 0x40007
    reg_status = 0x40009
    reg_config = 0x40008
    reg_read = 0x4000A

    # ---------------------------
    # Config params
    # ---------------------------
    lpm = 1
    ver = 2
    hor = 1
    psc = 1
    ut = 0

    # ---------------------------
    # CONFIG
    # ---------------------------
    log("Writing CONFIG...", verbose)

    word = (0 << 31 | ut << 13 | psc << 8 | hor << 4 | ver)
    ipbus.RODConfigWrite(reg_config, word)

    word = (1 << 31 | ut << 13 | psc << 8 | hor << 4 | ver)
    ipbus.RODConfigWrite(reg_config, word)

    # ---------------------------
    # RESET
    # ---------------------------
    log("Resetting...", verbose)
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0xF << 27))
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0 << 27))

    # ---------------------------
    # START
    # ---------------------------
    log("Starting...", verbose)
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0xF << 23))
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0 << 23))

    # ---------------------------
    # WAIT FOR READY
    # ---------------------------
    log("Waiting for READY...", verbose)

    rdy = 0
    start_time = time.time()
    timeout = 5

    while rdy != 0xFFFF:
        rdy = 0xFFFF & ipbus.ReadVal(reg_status)
        log(f"Status: 0x{rdy:04X}", verbose)

        if time.time() - start_time > timeout:
            log("ERROR: Timeout waiting for READY", verbose)
            break

        time.sleep(0.1)

    print("###################################")
    print("########### PREPARING #############")
    print("###################################")

    for rr in range(16):
        _ = ipbus.ReadVal(reg_read + rr)

    n = 4
    h = (64 // hor + 1) * n
    v = 127 if ver == 1 else (128 // ver + 1)

    log(f"Matrix size: lanes=16, v={v}, h={h}", verbose)

    eye = np.zeros((16, v, h))

    # ---------------------------
    # Acquisition
    # ---------------------------
    log("Starting acquisition...", verbose)

    for rr in range(16):
        log(f"Lane {rr}", verbose)

        for vv in range(v):
            for hh in range(0, h, n):
                aux = ipbus.ReadVal(reg_read + rr)

                sample = aux & 0xFFFF
                error = (aux >> 16) & 0xFFFF

                if sample == 0:
                    sample = 1

                value = float(error) / float(2 ** (psc + 1) * sample * 40)

                for ii in range(n):
                    eye[rr][vv][hh + ii] = value

    print("###################################")
    print("########### DONE ##################")
    print("###################################")

    return eye


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
# Plotext heatmap (fixed)
# ---------------------------
def plot_eye_heatmap(eye, lane=0, width=100, height=30):
    print(f"\nHeatmap lane {lane}\n")

    data = eye[lane]
    v, h = data.shape

    v_step = max(1, v // height)
    h_step = max(1, h // width)

    # ANSI grayscale (dark → bright)
    shades = " .:-=+*#%@"

    max_val = data.max() or 1

    for vv in range(0, v, v_step):
        line = ""
        for hh in range(0, h, h_step):
            val = data[vv][hh] / max_val
            idx = int(val * (len(shades) - 1))
            line += shades[idx] * 2  # stretch horizontally
        print(line)

def plot_eye_heatmap_color(eye, lane=0, width=100, height=30):
    print(f"\nColor heatmap lane {lane}\n")

    data = eye[lane]
    v, h = data.shape

    v_step = max(1, v // height)
    h_step = max(1, h // width)

    max_val = data.max() or 1

    for vv in range(0, v, v_step):
        line = ""
        for hh in range(0, h, h_step):
            val = data[vv][hh] / max_val

            # Map to 256-color (blue → red)
            color = int(16 + val * 200)

            line += f"\033[48;5;{color}m  \033[0m"

        print(line)

# ---------------------------
# Plotext grid (fixed)
# ---------------------------

# ---------------------------
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
if __name__ == "__main__":
    verbose = "--debug" in sys.argv

    log("===== START =====", verbose)

    try:
        eye = eye_func(verbose=verbose)

        # plot_eye_terminal(eye, lane=0)
        # plot_eye_heatmap(eye, lane=0)     # terminal heatmap
        # print("lenght:", len(eye))
        # print("eye:", eye)
        plot_eye_grid_terminal(eye)  # best visualization

        # Optional:
        # plot_eye_grid(eye)

    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        raise

    log("===== END =====", verbose)