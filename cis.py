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
DAC_CIS = 0xfc0

if options.bcid:
    bcid_l1a = format_number(options.bcid)

the_channel = format_number(options.channel) if options.channel else -1

pedestalDAC = 10
offset = 100
nDAC = 40
step = (4096 - offset) // nDAC
DAC_CIS_list = [(i * step) + offset for i in range(nDAC)]

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
# Pedestal configuration
# -------------------------------------------------
stableP = 1328
stableM = 2210

chargeP = stableP + pedestalDAC
chargeM = stableM - pedestalDAC

for adc in range(nchan):
    FPGA = (adc // 6 << 1) + (adc % 2)
    card = (adc // 2) % 3

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

# -------------------------------------------------
# Enable CIS
# -------------------------------------------------
BCID_discharge = 2200
BCID_charge = 500
bcid_l1a = BCID_discharge + 40

Gain_cis = 1

BCIDcharge = BCID_charge << 2
BCIDdischarge = BCID_discharge << 14
CIS_Enable = 1
CIS_Gain = Gain_cis << 1

# ppr.DB_Write_Val(md, cfb_cis_config, 3, BCIDdischarge + BCIDcharge + CIS_Gain + CIS_Enable)
#ppr.DB_Write_Val(md, cfb_cis_config, 0, 0)
ppr.AsyncWrite(md, cfb_cis_config, BCIDdischarge + BCIDcharge + CIS_Gain + CIS_Enable)
#ppr.AsyncWrite(md, cfb_cis_config, 0)

# -------------------------------------------------
# Trigger
# -------------------------------------------------
ppr.SyncClear()
ppr.SyncRest()
ppr.RODWrite(bcid_l1a & 0xFFF, 0x3)
ppr.SyncLoop(0)
ppr.SyncClear()
ppr.SyncRest()

# -------------------------------------------------
# RAW DATA READBACK
# -------------------------------------------------
the_data = ppr.RODReadMD(md=0, nchan=nchan, nsamp=nsamp, stride=32) 
# print(f"Raw data readback  {the_data}:")

# -------------------------------------------------
# Terminal display & ASCII bars with pulse info
# -------------------------------------------------
print("\nPulse values per channel:")
max_val = 0xFFF
for ch in range(12):
    hg = [(word >> 16) & 0xFFF for word in the_data[ch]]
    lg = [word & 0xFFF for word in the_data[ch]]
    
    # Calculate pulse info
    baseline_hg = hg[0]  # or min(hg)
    baseline_lg = lg[0]  # or min(lg)
    height_hg = max(hg) - baseline_hg
    height_lg = max(lg) - baseline_lg
    center_hg = sum(val * idx for idx, val in enumerate(hg)) / sum(hg) if sum(hg) else 0
    center_lg = sum(val * idx for idx, val in enumerate(lg)) / sum(lg) if sum(lg) else 0
    
    print(f"\nChannel {ch} | HG H={height_hg} C={center_hg:.1f} | LG H={height_lg} C={center_lg:.1f}:")
    
    for s in range(nsamp):
        word = the_data[ch][s]
        hg_val = (word >> 16) & 0xFFF
        lg_val = word & 0xFFF
        hg_str = color_text(hg_val, max_val, 'red')
        lg_str = color_text(lg_val, max_val, 'green')
        hg_bar = ascii_bar(hg_val, max_val)
        lg_bar = ascii_bar(lg_val, max_val)
        print(f"Sample {s:02d} | HG: {hg_str} {hg_bar} | LG: {lg_str} {lg_bar}")

# -------------------------------------------------
# Plotly 6x2 canvas with pulse info in legend
# -------------------------------------------------
fig = make_subplots(
    rows=2, cols=6,
    subplot_titles=[f"Ch {i}" for i in range(12)],
    horizontal_spacing=0.05, vertical_spacing=0.12
)

for ch in range(12):
    hg = [(word >> 16) & 0xFFF for word in the_data[ch]]
    lg = [word & 0xFFF for word in the_data[ch]]
    
    # Pulse info for legend
    height_hg = max(hg) - hg[0]
    height_lg = max(lg) - lg[0]
    center_hg = sum(val * idx for idx, val in enumerate(hg)) / sum(hg) if sum(hg) else 0
    center_lg = sum(val * idx for idx, val in enumerate(lg)) / sum(lg) if sum(lg) else 0
    
    row = 1 if ch < 6 else 2
    col = (ch % 6) + 1
    fig.add_trace(
        go.Scatter(
            y=hg,
            mode="lines+markers",
            name=f"HG H={height_hg} C={center_hg:.1f}",
            line=dict(color='red')
        ),
        row=row, col=col
    )
    fig.add_trace(
        go.Scatter(
            y=lg,
            mode="lines+markers",
            name=f"LG H={height_lg} C={center_lg:.1f}",
            line=dict(color='green')
        ),
        row=row, col=col
    )

fig.update_layout(
    height=700, width=1800,
    title_text="CIS Scan All Channels",
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.2,
        xanchor="center",
        x=0.5
    )
)

plot_file = os.path.join(plotdir, f"CIS_scan_{now.strftime('%Y%m%d_%H%M')}.html")
fig.write_html(plot_file)
print(f"\nPlot saved to {plot_file}")