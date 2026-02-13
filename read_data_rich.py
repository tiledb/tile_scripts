#!/usr/bin/env python3
import time
import itertools
import Herakles
from db_ppr_ipbus import *
from rich.live import Live
from rich.panel import Panel
from rich.console import Group
from rich.table import Table
from rich.layout import Layout

# ------------------ CONFIG ------------------

HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

nsamp = 16
nchanperMD = 12
firstMD = 0
nMD = 1  # number of modules to display

bcid_l1a = 2246
read_interval = 2.0  # seconds between refresh

# ------------------ COLOR MAPPING ------------------

def value_to_color(val, vmin=0, vmax=4095):
    val = max(vmin, min(vmax, val))
    norm = (val - vmin) / (vmax - vmin)
    color_code = int(21 + norm * (196 - 21))
    return f"color({color_code})"

# ------------------ CHANNEL PANEL BUILDER ------------------

def build_channel_panel(md, ch, hg_data, lg_data):
    """Build a Panel for a single channel showing HG + LG samples."""
    table = Table.grid(expand=True)
    table.add_column(justify="right")

    # HG row
    hg_row = " ".join(f"[{value_to_color(v)}]{v}[/{value_to_color(v)}]" for v in hg_data[md * nchanperMD + ch])
    table.add_row(f"HG: {hg_row}")

    # LG row
    lg_row = " ".join(f"[{value_to_color(v)}]{v}[/{value_to_color(v)}]" for v in lg_data[md * nchanperMD + ch])
    table.add_row(f"LG: {lg_row}")

    return Panel(table, title=f"MD{md} Ch{ch}", border_style="green", expand=True)

# ------------------ STATUS TABLE ------------------

def build_status_line(led, status_text="Idle", current_md="-", last_L1ID="-", last_BCID="-"):
    """Return a single-line table for the status bar."""
    table = Table.grid(expand=True)
    table.add_column("LED", width=2, justify="center")
    table.add_column("Status", width=12, justify="left")
    table.add_column("Current MD", width=10, justify="center")
    table.add_column("Last L1A ID", width=12, justify="center")
    table.add_column("Last BCID", width=12, justify="center")
    table.add_row(
        led,
        status_text,
        str(current_md),
        str(last_L1ID),
        str(last_BCID)
    )
    return table

# ------------------ INITIALIZATION ------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = Herakles.Uhal(
    f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001"
)
ppr = PPr(ipbus)
feb = FEB(ppr)

print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")
time.sleep(1)

# ------------------ LIVE DASHBOARD ------------------

led_cycle = itertools.cycle(["🔴", "🟡", "🟢"])

# ---- ROOT LAYOUT (create once) ----
root = Layout()
root.split_column(
    Layout(name="status", size=3),  # single-line status bar
    *[Layout(name=f"md{md}") for md in range(firstMD, firstMD + nMD)]
)

# Initialize module panels with placeholders
for md in range(firstMD, firstMD + nMD):
    root[f"md{md}"].update(Panel("Waiting for data...", title=f"Module {md}", border_style="cyan"))

# Start live display
with Live(root, screen=True, refresh_per_second=4) as live:

    try:
        while True:

            # ---- STATUS: Sending L1A trigger ----
            led = next(led_cycle)
            last_L1ID = ppr.read(PPrReg.LAST_EVT_L1ID)
            last_BCID = ppr.read(PPrReg.LAST_EVT_BCID)
            root["status"].update(
                Panel(build_status_line(led, status_text="Sending L1A", current_md="-",
                                        last_L1ID=last_L1ID, last_BCID=last_BCID),
                      title="Status", border_style="magenta")
            )
            live.refresh()

            feb.send_L1A(bcid_l1a, 3)

            # ---- READ DATA ----
            all_hg_data = [[] for _ in range(nchanperMD * (firstMD + nMD))]
            all_lg_data = [[] for _ in range(nchanperMD * (firstMD + nMD))]

            for md in range(firstMD, firstMD + nMD):
                # Update status while reading this MD
                led = next(led_cycle)
                last_L1ID = ppr.read(PPrReg.LAST_EVT_L1ID)
                last_BCID = ppr.read(PPrReg.LAST_EVT_BCID)
                root["status"].update(
                    Panel(build_status_line(led, status_text="Reading", current_md=md,
                                            last_L1ID=last_L1ID, last_BCID=last_BCID),
                          title="Status", border_style="magenta")
                )
                live.refresh()

                # Read HG/LG for all channels
                for ch in range(nchanperMD):
                    hg = ppr.get_data_HG(md, ch, nsamp)
                    lg = ppr.get_data_LG(md, ch, nsamp)
                    idx = md * nchanperMD + ch
                    all_hg_data[idx] = list(hg)
                    all_lg_data[idx] = list(lg)

            # ---- UPDATE MODULE PANELS ----
            for md in range(firstMD, firstMD + nMD):
                channel_panels = [build_channel_panel(md, ch, all_hg_data, all_lg_data)
                                  for ch in range(nchanperMD)]
                group = Group(*channel_panels)
                root[f"md{md}"].update(
                    Panel(group, title=f"Module {md}", border_style="cyan", expand=True)
                )

            # ---- STATUS: Idle ----
            led = next(led_cycle)
            last_L1ID = ppr.read(PPrReg.LAST_EVT_L1ID)
            last_BCID = ppr.read(PPrReg.LAST_EVT_BCID)
            root["status"].update(
                Panel(build_status_line(led, status_text="Idle", current_md="-",
                                        last_L1ID=last_L1ID, last_BCID=last_BCID),
                      title="Status", border_style="magenta")
            )

            live.refresh()
            time.sleep(read_interval)

    except KeyboardInterrupt:
        pass
