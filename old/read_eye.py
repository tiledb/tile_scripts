#!/usr/bin/env python3
import sys
import time
import numpy as np
import Herakles
import datetime


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
                "tcp://192.168.0.201:10203?target=192.168.0.2:50001"
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
    hor = 2
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

def compute_metrics(data, threshold=1e-6):
    """
    Returns open area, horizontal opening, vertical opening
    Handles empty diagrams correctly.
    """

    # If the diagram is all zeros, return zeros
    if np.all(data == 0):
        return 0.0, 0, 0

    v, h = data.shape
    max_val = data.max() or 1
    thr = threshold if threshold > 0 else max_val * 0.01

    mask = data < thr

    # Open area
    open_area = np.sum(mask) / (v * h)

    # Horizontal opening (max consecutive True in any row)
    max_h_open = 0
    for row in mask:
        count = 0
        best = 0
        for val in row:
            if val:
                count += 1
                best = max(best, count)
            else:
                count = 0
        max_h_open = max(max_h_open, best)

    # Vertical opening (max consecutive True in any column)
    max_v_open = 0
    for col in mask.T:
        count = 0
        best = 0
        for val in col:
            if val:
                count += 1
                best = max(best, count)
            else:
                count = 0
        max_v_open = max(max_v_open, best)

    return open_area, max_h_open, max_v_open

def plot_eye_grid_terminal(eye, width=25, height=10, threshold=1e-6):
    """
    Plot 4x4 grid of eye diagrams with:
    - Lane number
    - Eye opening (H, V)
    - Open area (%)

    threshold: value below which a point is considered "open"
    """
    for row in range(4):

        block_lines = None
        header_lines = ["", ""]  # two lines per lane

        for col in range(4):
            lane = row * 4 + col
            data = eye[lane]

            v, h = data.shape

            v_step = max(1, v // height)
            h_step = max(1, h // width)

            max_val = data.max() or 1

            # ---- Compute metrics ----
            open_area, h_open, v_open = compute_metrics(data)

            # ---- Header text ----
            header1 = f"L{lane:02d}"
            header2 = f"H{h_open:02d} V{v_open:02d} A{open_area*100:4.1f}%"

            header_lines[0] += f"{header1:^{width}}  "
            header_lines[1] += f"{header2:^{width}}  "

            # ---- Build heatmap ----
            lane_lines = []

            for vv in range(0, v, v_step):
                line = ""
                for hh in range(0, h, h_step):
                    val = data[vv][hh] / max_val

                    color = int(16 + val * 200)
                    line += f"\033[48;5;{color}m \033[0m"

                lane_lines.append(line)

            # Initialize block storage
            if block_lines is None:
                block_lines = [""] * len(lane_lines)

            min_len = min(len(block_lines), len(lane_lines))

            for i in range(min_len):
                block_lines[i] += lane_lines[i] + "  "

        # ---- Print headers ----
        for hline in header_lines:
            print(hline)

        # ---- Print eyes ----
        for line in block_lines:
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