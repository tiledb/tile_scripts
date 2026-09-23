#!/usr/bin/env python3
"""
Eye diagram readback following test_fca/eye_db.py acquisition,
with terminal visualization styled like tile_scripts/read_eye.py.
"""
import argparse
import time
import datetime
import numpy as np
import Herakles
from itertools import groupby
from scipy.special import erfc

DEFAULT_N_EYES = 12
MAX_N_EYES = 16


# ---------------------------
# Logging helpers
# ---------------------------
def step(msg):
    """Always print progress to the terminal."""
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def log(msg, verbose):
    if verbose:
        step(msg)


# ---------------------------
# IPbus (eye_db style)
# ---------------------------
class IPbus:
    def __init__(self, verbose=False):
        self.verbose = verbose
        step("Connecting IPbus (192.168.0.201 -> 192.168.0.3:50001)...")
        self.ipbus = Herakles.Uhal(
            "tcp://192.168.0.201:10203?target=192.168.0.3:50001"
        )
        self.ipbus.SetVerbose(verbose)
        step("IPbus connected")

    def RODConfigWrite(self, add, val):
        log(f"[WRITE] addr=0x{add:X}, val=0x{val:X}", self.verbose)
        self.ipbus.Write(add, val)

    def ReadVal(self, add):
        log(f"[READ] addr=0x{add:X}", self.verbose)
        val = self.ipbus.Read(add, 1)
        log(f"[READ DONE] -> {val}", self.verbose)
        return val


# ---------------------------
# Eye acquisition (from eye_db.py)
# ---------------------------
def eye_func(n_eyes=DEFAULT_N_EYES, verbose=False):
    """
    Acquire eye diagrams using the working test_read_eye.py sequence
    (same registers/config that succeed on this setup).
    Returns eye[lane][v][h] with BER-normalized values.

    n_eyes: number of eye/lane diagrams to read out (1 .. MAX_N_EYES).
    """
    if not (1 <= n_eyes <= MAX_N_EYES):
        raise ValueError(f"n_eyes must be in 1..{MAX_N_EYES}, got {n_eyes}")

    step("===== eye acquisition start =====")
    ipbus = IPbus(verbose=verbose)

    # Registers
    reg_control = 0x40007
    reg_status = 0x40009
    reg_config = 0x40008
    reg_read = 0x4000A

    # Config params — match working test_read_eye.py (not eye_db defaults)
    # eye_db used hor=2, psc=3; those leave status stuck ~0x001E on this setup
    lpm = 1  # 0=DFE (2nd pass), 1=LPM
    ver = 2
    hor = 1
    psc = 1
    ut = 0

    max_link = n_eyes
    step(f"Will read {max_link} eye(s)")

    # CONFIG
    step(f"Writing CONFIG (ver={ver}, hor={hor}, psc={psc}, ut={ut}, lpm={lpm})...")
    word = (0 << 31 | ut << 13 | psc << 8 | hor << 4 | ver)
    ipbus.RODConfigWrite(reg_config, word)
    word = (1 << 31 | ut << 13 | psc << 8 | hor << 4 | ver)
    ipbus.RODConfigWrite(reg_config, word)
    step("CONFIG done")

    # RESET
    step("Resetting eye scan...")
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0xF << 27))
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0 << 27))
    step("RESET done")

    # START
    step("Starting eye scan...")
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0xF << 23))
    ipbus.RODConfigWrite(reg_control, (1 << 31 | 0 << 23))
    step("START done")

    # WAIT FOR READY — same as test_read_eye: short timeout, then continue
    step("Waiting for READY (status == 0xFFFF)...")
    rdy = 0
    start_time = time.time()
    timeout = 5
    last_print = 0.0
    while rdy != 0xFFFF:
        rdy = 0xFFFF & ipbus.ReadVal(reg_status)
        elapsed = time.time() - start_time
        if elapsed - last_print >= 1.0 or rdy == 0xFFFF:
            step(f"  status=0x{rdy:04X}  elapsed={elapsed:.1f}s")
            last_print = elapsed
        if elapsed > timeout:
            step(
                f"READY timeout after {timeout}s (last status=0x{rdy:04X}); "
                "continuing like test_read_eye.py"
            )
            break
        time.sleep(0.1)
    else:
        step("READY asserted")

    print("###################################")
    print("########### PREPARING #############")
    print("###################################")

    # Flush pipeline (same as test_read_eye / eye_db)
    step("Flushing readout pipeline (16 reads)...")
    for rr in range(16):
        _ = ipbus.ReadVal(reg_read + rr)
    step("Flush done")

    n = 4
    h = (64 // hor + 1) * n
    v = 127 if ver == 1 else (128 // ver + 1)

    step(f"Matrix size: lanes={max_link}, v={v}, h={h} (reads/lane={v * (h // n)})")
    eye = np.zeros((max_link, v, h))

    # Acquisition — BER formula like test_read_eye.py
    step("Starting acquisition...")
    for rr in range(max_link):
        t0 = time.time()
        step(f"  Reading lane {rr + 1}/{max_link}...")
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
        step(f"  Lane {rr + 1}/{max_link} done ({time.time() - t0:.1f}s)")

    print("###################################")
    print("########### DONE ##################")
    print("###################################")
    step("===== eye acquisition done =====")

    return eye


# ---------------------------
# Metrics (from read_eye.py)
# ---------------------------
def compute_metrics(data, threshold=1e-6):
    if np.all(data == 0):
        return {
            "open_area": 0.0,
            "max_h_open": 0,
            "max_v_open": 0,
            "eye_height": 0.0,
            "rms_jitter": 0.0,
            "peak_to_peak_jitter": 0.0,
            "q_factor": 0.0,
            "snr": 0.0,
            "crossing_point": 0.5,
            "ber": 1.0,
        }

    v, h = data.shape
    max_val = data.max()
    min_val = data.min()
    thr = threshold if threshold > 0 else max_val * 0.01

    mask = data >= thr
    open_area = np.sum(mask) / (v * h)

    max_h_open = max(
        (sum(1 for _ in g) for row in mask for k, g in groupby(row) if k),
        default=0,
    )
    max_v_open = max(
        (sum(1 for _ in g) for col in mask.T for k, g in groupby(col) if k),
        default=0,
    )

    eye_height = max_val - min_val

    mid_val = (max_val + min_val) / 2
    crossing_positions = []
    for row in data:
        for i in range(1, len(row)):
            if (row[i - 1] < mid_val <= row[i]) or (row[i - 1] >= mid_val > row[i]):
                crossing_positions.append(i)
    if crossing_positions:
        rms_jitter = np.std(crossing_positions)
        peak_to_peak_jitter = np.max(crossing_positions) - np.min(crossing_positions)
        crossing_point = np.mean(crossing_positions) / h
    else:
        rms_jitter = 0.0
        peak_to_peak_jitter = 0.0
        crossing_point = 0.5

    ones = data > mid_val
    zeros = data <= mid_val
    mu1, sigma1 = (data[ones].mean(), data[ones].std()) if np.any(ones) else (0, 1)
    mu0, sigma0 = (data[zeros].mean(), data[zeros].std()) if np.any(zeros) else (0, 1)
    q_factor = (mu1 - mu0) / (sigma1 + sigma0) if (sigma1 + sigma0) > 0 else 0
    snr = eye_height / (np.std(data) or 1)
    ber_estimate = 0.5 * erfc(q_factor / np.sqrt(2)) if q_factor > 0 else 1.0

    return {
        "open_area": open_area,
        "max_h_open": max_h_open,
        "max_v_open": max_v_open,
        "eye_height": eye_height,
        "rms_jitter": rms_jitter,
        "peak_to_peak_jitter": peak_to_peak_jitter,
        "q_factor": q_factor,
        "snr": snr,
        "crossing_point": crossing_point,
        "ber": ber_estimate,
    }


# ---------------------------
# Terminal grid plot (read_eye style, all acquired lanes)
# ---------------------------
def plot_eye_grid_terminal(eye, width=25, height=10, threshold=1e-6):
    """
    Plot eye diagrams in rows of 4 (QSFP grouping like eye_db matplotlib figures).
    Metrics printed above each mini eye diagram.
    """
    lanes_per_row = 4
    num_lanes = len(eye)

    for row in range((num_lanes + lanes_per_row - 1) // lanes_per_row):
        qsfp = row + 1
        print(f"========== QSFP {qsfp} ==========")

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
            metrics_lines = [
                f"QSFP{qsfp} L{col + 1}",
                f"Open Area : {metrics['open_area'] * 100:5.1f}%",
                f"Max H     : {metrics['max_h_open']}",
                f"Max V     : {metrics['max_v_open']}",
                f"Eye H     : {metrics['eye_height']:.2f}",
                f"RMS J     : {metrics['rms_jitter']:.2f}",
                f"P2P J     : {metrics['peak_to_peak_jitter']:.2f}",
                f"Q-factor  : {metrics['q_factor']:.2f}",
                f"SNR       : {metrics['snr']:.2f}",
                f"Cross Pt  : {metrics['crossing_point']:.2f}",
                f"BER       : {metrics['ber']:.1e}",
            ]
            lane_metrics.append(metrics_lines)

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

        num_metric_lines = max(len(m) for m in lane_metrics)
        for i in range(num_metric_lines):
            line = ""
            for metrics_lines in lane_metrics:
                if i < len(metrics_lines):
                    line += f"{metrics_lines[i]:<{width}}  "
                else:
                    line += " " * width + "  "
            print(line)

        for i in range(max_eye_lines):
            line = ""
            for eye_lines in lane_lines_list:
                if i < len(eye_lines):
                    line += f"{eye_lines[i]:<{width}}  "
                else:
                    line += " " * width + "  "
            print(line)

        print()


# ---------------------------
# CLI
# ---------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Eye diagram readback (eye_db sequence) with terminal plot."
    )
    parser.add_argument(
        "-n",
        "--n-eyes",
        type=int,
        default=DEFAULT_N_EYES,
        metavar="N",
        help=f"number of eyes/lanes to acquire (1..{MAX_N_EYES}, default: {DEFAULT_N_EYES})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="verbose IPbus read/write logging",
    )
    args = parser.parse_args()
    if not (1 <= args.n_eyes <= MAX_N_EYES):
        parser.error(f"--n-eyes must be between 1 and {MAX_N_EYES}")
    return args


# ---------------------------
# Main
# ---------------------------
if __name__ == "__main__":
    args = parse_args()

    step("===== START =====")
    step(f"n_eyes={args.n_eyes}  debug={args.debug}")

    try:
        eye = eye_func(n_eyes=args.n_eyes, verbose=args.debug)
        step("Rendering terminal eye grid...")
        plot_eye_grid_terminal(eye)
        step("Plot done")
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        raise

    step("===== END =====")
