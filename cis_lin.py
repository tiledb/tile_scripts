#!/usr/bin/env python3

# tilecal libs
from db_lib import *
from db_ppr_ipbus import *

# python libs
import sys
import time
import datetime
import os
from optparse import OptionParser
import Herakles
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# -------------------------------------------------
# Terminal color helpers
# -------------------------------------------------
def color_text(value, max_val, color='green'):
    """
    Return colored string for terminal:
    Higher values are darker (bold)
    """
    intensity = int((value / max_val) * 255)
    intensity = min(255, max(0, intensity))
    if color == 'green':
        return f"\033[38;2;0;{intensity};0m{value:4}\033[0m"
    elif color == 'red':
        return f"\033[38;2;{intensity};0;0m{value:4}\033[0m"
    else:
        return str(value)

def ascii_bar(value, max_val, length=20):
    filled = int((value / max_val) * length)
    return '█' * filled + '-' * (length - filled)

# -------------------------------------------------
# Filename & plot folder
# -------------------------------------------------
now = datetime.datetime.now()
filename = "cis" + now.strftime("_date_%Y-%m-%d_time_%H-%M") + ".root"

# -------------------------------------------------
# Options
# -------------------------------------------------
parser = OptionParser()
parser.add_option("-c", "--channel", dest="channel")
parser.add_option("-p", "--plotdir", dest="plotdir", help="Directory to save plots")
parser.add_option("-s", "--samples", dest="samples")
parser.add_option("-b", "--bcid", dest="bcid")
parser.add_option("--ppripaddress", dest="ppripaddress")
parser.add_option("--hostipaddress", dest="hostipaddress")

(options, args) = parser.parse_args()

plotdir = options.plotdir or "./plots/cis"
os.makedirs(plotdir, exist_ok=True)

# -------------------------------------------------
# IP addresses
# -------------------------------------------------
PPrIPaddressServer = options.ppripaddress or "192.168.0.2"
HostIPaddressServer = options.hostipaddress or "192.168.0.201"

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ppr = IPbus(HostIPaddressServer, PPrIPaddressServer)

fw = ppr.ReadVal(1)
print(f"Connected. FW version: {hex(fw)}")

# -------------------------------------------------
# Constants
# -------------------------------------------------
BCID_discharge = 2200
BCID_charge = 500
bcid_l1a = BCID_discharge + 44

Gain_cis = 0

if options.bcid:
    bcid_l1a = format_number(options.bcid)

the_channel = format_number(options.channel) if options.channel else -1

pedestalDAC = 10
offset = 0
nsteps = 50  # Number of steps from 0 to 4096
step = 4096 // nsteps
configured_heights = [i * step for i in range(nsteps)]

nchan = 12
md = 0

nsamp = ppr.ReadVal(0x9F) & 0xFF
if options.samples:
    nsamp = format_number(options.samples)
if nsamp == 0:
    nsamp = 16

# -------------------------------------------------
# Disable external TTC, enable internal
# -------------------------------------------------
ppr.RODConfigWrite(0x2, 0x87)
ppr.RODConfigWrite(0x4, 0x0)
ppr.RODConfigWrite(0x5, 0x0)

DisableDCS = 1
ConfigDCS = (DisableDCS << 17)
ppr.RODConfigWrite(0x6, ConfigDCS)

# -------------------------------------------------
# Pedestal constants
# -------------------------------------------------
stableP = 0
stableM = 2210

# -------------------------------------------------
# Enable CIS (basic setup, same for all steps)
# -------------------------------------------------
BCIDcharge = BCID_charge << 2
BCIDdischarge = BCID_discharge << 14
CIS_Enable = 1
CIS_Gain = Gain_cis << 1
cfb_cis_config = 0x0  # define properly if needed

ppr.AsyncWrite(md, cfb_cis_config,
               BCIDdischarge + BCIDcharge + CIS_Gain + CIS_Enable)

# -------------------------------------------------
# Arrays to store measured heights
# -------------------------------------------------
measured_HG = [[0]*nsteps for _ in range(nchan)]
measured_LG = [[0]*nsteps for _ in range(nchan)]

# -------------------------------------------------
# Sweep pulse heights
# -------------------------------------------------
for idx, cfg_height in enumerate(configured_heights):
    print(f"\n=== Configured pulse height {cfg_height} ({idx+1}/{nsteps}) ===")
    
    for adc in range(nchan):
        FPGA = (adc // 6 << 1) + (adc % 2)
        card = (adc // 2) % 3
        
        chargeP = stableP #+ cfg_height
        chargeM = stableM - cfg_height

        for base, value in [(0x6000, chargeP), (0x7000, chargeM),
                            (0x4000, chargeP), (0x5000, chargeM)]:
            ppr.AsyncWrite(md, 0x1, 0x8000000)
            time.sleep(0.0001)
            ppr.AsyncWrite(md, 0x1, (1 << 22) + (FPGA << 18) + (card << 16) + base + int(value))
            time.sleep(0.0001)
            ppr.AsyncWrite(md, 0x1, 0x8000000)

        # Load LG / HG
        for load in [0xC000, 0xD000]:
            ppr.AsyncWrite(md, 0x1, 0x80000000)
            time.sleep(0.0001)
            ppr.AsyncWrite(md, 0x1, (1 << 22) + (FPGA << 18) + (card << 16) + load)
            time.sleep(0.0001)

    # Trigger readout
    ppr.SyncClear()
    ppr.SyncRest()
    ppr.RODWrite(bcid_l1a & 0xFFF, 0x3)
    ppr.SyncLoop(0)
    ppr.SyncClear()
    ppr.SyncRest()

    the_data = ppr.RODReadMD(md=0, nchan=nchan, nsamp=nsamp, stride=32)

    # Extract and display pulse heights
    max_val = 0xFFF
    for ch in range(nchan):
        hg = [(word >> 16) & 0xFFF for word in the_data[ch]]
        lg = [word & 0xFFF for word in the_data[ch]]
        baseline_hg = hg[0]
        baseline_lg = lg[0]
        height_hg = max(hg) - baseline_hg
        height_lg = max(lg) - baseline_lg
        measured_HG[ch][idx] = height_hg
        measured_LG[ch][idx] = height_lg

        # Terminal ASCII display
        hg_str = color_text(height_hg, max_val, 'red')
        lg_str = color_text(height_lg, max_val, 'green')
        hg_bar = ascii_bar(height_hg, max_val)
        lg_bar = ascii_bar(height_lg, max_val)
        print(f"Ch {ch:02d} | HG: {hg_str} {hg_bar} | LG: {lg_str} {lg_bar}")

# -------------------------------------------------
# Plot configured vs measured heights
# -------------------------------------------------
fig = make_subplots(
    rows=2, cols=6,
    subplot_titles=[f"Ch {i}" for i in range(nchan)],
    horizontal_spacing=0.05, vertical_spacing=0.12
)

for ch in range(nchan):
    row = 1 if ch < 6 else 2
    col = (ch % 6) + 1
    fig.add_trace(
        go.Scatter(
            x=configured_heights,
            y=measured_HG[ch],
            mode='lines+markers',
            name='HG',
            line=dict(color='red')
        ),
        row=row, col=col
    )
    fig.add_trace(
        go.Scatter(
            x=configured_heights,
            y=measured_LG[ch],
            mode='lines+markers',
            name='LG',
            line=dict(color='green')
        ),
        row=row, col=col
    )

fig.update_layout(
    height=700, width=1800,
    title_text="CIS Configured vs Measured Pulse Heights",
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.2,
        xanchor="center",
        x=0.5
    )
)

plot_file = os.path.join(plotdir, f"CIS_sweep_{now.strftime('%Y%m%d_%H%M')}.html")
fig.write_html(plot_file)
print(f"\nPlot saved to {plot_file}")
