#!/usr/bin/env python3
"""ADC pattern programming / readout for TileCal DB via PPr IPbus.

Python 3.7 compatible. Register maps come from tile_scripts/db_lib.py;
IPbus comes from tile_scripts/db7_flask/db_ppr_ipbus.py.
"""
from __future__ import print_function

import argparse
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_DB7_FLASK = os.path.join(_HERE, "db7_flask")

# Load tile_scripts/db_lib.py first so it stays in sys.modules when the
# flask IPbus module does `from db_lib import *`.
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from db_lib import *  # noqa: E402

# Prefer the flask IPbus implementation over tile_scripts/db_ppr_ipbus.py.
sys.path.insert(0, _DB7_FLASK)
from db_ppr_ipbus import DBReg, FEB, IPbus, PPr, PPrReg  # noqa: E402

FPGA_ALL = 4   # broadcast all FPGAs
TUBE_ALL = 3   # broadcast all 3-in-1 cards

# Per-ADC FPGA / 3-in-1 card (same mapping as DBReg, plus broadcast entries)
fpga = list(DBReg.FPGA) + [FPGA_ALL]
tube = list(DBReg.FPGA_CHANNEL) + [TUBE_ALL]

nchan = 12
nsamp = 16  # same pipeline depth as tile_scripts/read_data.py
md = 0
bcid_l1a = 2246  # same L1A BCID as tile_scripts/read_data.py

the_strobe_lenght = 4
the_strobe_lenght_pos = 16

DEFAULT_HOST_IP = "192.168.0.201"
DEFAULT_PPR_IP = "192.168.0.3"


def write_mb_adc_cmd(ipbus, md_idx, xcmd):
    """Pulse cfb_mb_adc_config with xcmd, then clear (FPGA 0 = broadcast)."""
    ipbus.DB_Write_Val(md_idx, 0, cfb_mb_adc_config, xcmd, 0)
    time.sleep(0.3)
    ipbus.DB_Write_Val(md_idx, 0, cfb_mb_adc_config, 0, 0)
    time.sleep(0.3)


def mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd, adr=0, data=0, cmd_bits=3):
    """Build a mainboard ADC serial command word."""
    word = (T << 23) | (E << 22) | (B << 21) | (FPGA << 18) | (TUBE << 16)
    word |= (cmd << (12 if cmd_bits == 4 else 13))
    if cmd_bits == 3:
        word |= (adr << 8) | (data & 0xFF)
    return word


def format_sample_rows(samples, width=8):
    hex_vals = [hex(v) for v in samples]
    bin_vals = [format(v, "#014b") for v in samples]
    hex_lines = []
    bin_lines = []
    for i in range(0, len(samples), width):
        hex_lines.append(" ".join(hex_vals[i:i + width]))
        bin_lines.append(" ".join(bin_vals[i:i + width]))
    return hex_lines, bin_lines


def print_heatmap_hg_lg(md_idx, hg_data, lg_data, nchanperMD=12, nsamp=16,
                        vmin=0, vmax=4095):
    """Same channel/sample grid as tile_scripts/read_data.py."""

    def value_to_color(val):
        val = max(vmin, min(vmax, val))
        norm = (val - vmin) / float(vmax - vmin)
        color_code = int(21 + norm * (196 - 21))
        return "\033[48;5;{}m".format(color_code)

    reset = "\033[0m"
    header = "Ch  | Gain | "
    for s in range(nsamp):
        header += "{:4d} ".format(s)
    print(header)
    print("-" * len(header))

    for ch in range(nchanperMD):
        idx = md_idx * nchanperMD + ch
        row = "{:02d}  | HG   | ".format(ch)
        for val in hg_data[idx]:
            row += "{}{:4d}{} ".format(value_to_color(val), val, reset)
        print(row)
        row = "{:02d}  | LG   | ".format(ch)
        for val in lg_data[idx]:
            row += "{}{:4d}{} ".format(value_to_color(val), val, reset)
        print(row)
    print()


def _write_sample_block(logf, label, samples, width=8):
    for i in range(0, len(samples), width):
        chunk = samples[i:i + width]
        prefix = label if i == 0 else " " * len(label)
        logf.write(prefix + " ".join("%x" % v for v in chunk) + "\n")


def pulse_strobe(ipbus, md_idx, value):
    ipbus.DB_Write_Val(md_idx, 0, cfb_strobe_reg, value, 0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Set / reset ADC test patterns and optionally read them back."
    )
    parser.add_argument(
        "-p", "--pattern",
        help="Pattern value (ADC counts), e.g. 0xabc or 1234",
    )
    parser.add_argument(
        "-r", "--reset",
        action="store_true",
        help="Reset ADC to normal (parallel) state",
    )
    parser.add_argument(
        "-a", "--adc_readout_reset",
        action="store_true",
        help="Reset ADC readout",
    )
    parser.add_argument(
        "-d", "--adc_config_driver",
        action="store_true",
        help="Reset ADC config driver",
    )
    parser.add_argument(
        "-s", "--show_readout",
        action="store_true",
        help="Show ADC readout after sending L1As",
    )
    parser.add_argument(
        "-i", "--ppripaddress",
        dest="ppripaddress",
        help="PPr IP address (default: {})".format(DEFAULT_PPR_IP),
    )
    parser.add_argument(
        "--hostipaddress",
        dest="hostipaddress",
        help="ControlHub / host IP address (default: {})".format(DEFAULT_HOST_IP),
    )
    parser.add_argument(
        "-t", "--tcpip",
        action="store_true",
        help=argparse.SUPPRESS,  # always uses ControlHub; kept for old CLIs
    )
    return parser.parse_args()


def set_adc_pattern(ipbus, md_idx, pattern):
    T, E, B = 1, 0, 0
    FPGA = FPGA_ALL
    TUBE = TUBE_ALL

    # SET SERIAL MODE
    xcmd = mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd=3, data=0)
    print("REG0=", hex(0), "xcmd=", hex(xcmd))
    write_mb_adc_cmd(ipbus, md_idx, xcmd)

    # SET ADC CONTROL REGISTER 2
    data = 0xB6
    xcmd = mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd=4, adr=2, data=data)
    print("REG2=", hex(data), "xcmd=", hex(xcmd))
    write_mb_adc_cmd(ipbus, md_idx, xcmd)

    # SET ADC CONTROL REGISTER 3
    data = 0x80 + (pattern >> 6)
    xcmd = mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd=4, adr=3, data=data)
    print("REG3=", hex(data), "xcmd=", hex(xcmd))
    write_mb_adc_cmd(ipbus, md_idx, xcmd)

    # SET ADC CONTROL REGISTER 4
    data = (pattern << 2) & 0xFF
    xcmd = mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd=4, adr=4, data=data)
    print("REG4=", hex(data), "xcmd=", hex(xcmd))
    write_mb_adc_cmd(ipbus, md_idx, xcmd)


def reset_adcs(ipbus, md_idx, do_readout_reset):
    T, E, B = 1, 0, 0
    for adc in range(12):
        FPGA = fpga[adc]
        TUBE = tube[adc]
        xcmd = mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd=3, data=0)
        print(" SET pattern ---- xcmd=", hex(xcmd), " adc=", adc)
        write_mb_adc_cmd(ipbus, md_idx, xcmd)

        # SET ADC CONTROL REGISTER 3 - data taking mode
        xcmd = mb_adc_xcmd(T, E, B, FPGA, TUBE, cmd=4, adr=3, data=0x00)
        print("Config ADC in normal operation mode: ", adc)
        write_mb_adc_cmd(ipbus, md_idx, xcmd)

    FPGA = fpga[11]
    TUBE = tube[11]
    xcmd = mb_adc_xcmd(0, 1, 0, FPGA, TUBE, cmd=0xF, cmd_bits=4)
    print(" Global Reset ---- xcmd=", hex(xcmd))
    write_mb_adc_cmd(ipbus, md_idx, xcmd)

    if not do_readout_reset:
        print("No ADC Readout reset issued...")
        return

    print("Resseting ADC Readout...")
    the_value = (1 << 7) | (the_strobe_lenght << the_strobe_lenght_pos)
    pulse_strobe(ipbus, md_idx, the_value)


def show_adc_readout(ipbus, md_idx, pattern, start, logf):
    """L1A + pipeline read, copied from tile_scripts/read_data.py.

    Uses PPr.get_data_HG / get_data_LG and FEB.send_L1A on the same Uhal
    connection. Does not touch TTC/trigger — that is what read_data.py does.
    """
    ppr = PPr(ipbus.ipbus)
    feb = FEB(ppr)

    print("Firmware version: 0x{:08X}".format(ppr.get_firmware_version()))
    print("Sending L1A (bcid={}) then reading HG/LG pipeline...".format(bcid_l1a))

    ERR = 0
    n_events = 51

    for nevnt in range(n_events):
        feb.send_L1A(bcid_l1a, 3)

        all_hg_data = [[] for _ in range(nchan)]
        all_lg_data = [[] for _ in range(nchan)]

        for ch in range(nchan):
            hg = list(ppr.get_data_HG(md_idx, ch, nsamp))
            lg = list(ppr.get_data_LG(md_idx, ch, nsamp))
            all_hg_data[ch] = hg
            all_lg_data[ch] = lg

            if pattern is not None:
                for a in range(len(hg)):
                    if (hg[a] & 0xFFF) != pattern:
                        ERR += 1
                    if (lg[a] & 0xFFF) != pattern:
                        ERR += 1

        if nevnt < 1:
            last_l1id = ppr.get_counter_last_event_L1ID()
            last_bcid = ppr.get_counter_last_event_BCID()
            print("Last L1ID={}  Last BCID={}".format(last_l1id, last_bcid))
            print("\n========== MD{} HG / LG SAMPLE HEATMAP ==========".format(md_idx))
            print_heatmap_hg_lg(
                0, all_hg_data, all_lg_data,
                nchanperMD=nchan, nsamp=nsamp, vmin=0, vmax=4095,
            )
            for ch in range(nchan):
                hg = all_hg_data[ch]
                lg = all_lg_data[ch]
                lg_hex, lg_bin = format_sample_rows(lg)
                hg_hex, hg_bin = format_sample_rows(hg)
                print(" *********************************************************************************************************************************************")
                print("adc=", ch)
                print(" LGsamples=", lg_hex[0])
                for line in lg_hex[1:]:
                    print("           ", line)
                print(" HGsamples=", hg_hex[0])
                for line in hg_hex[1:]:
                    print("           ", line)
                print(" LGsamples=", lg_bin[0])
                for line in lg_bin[1:]:
                    print("           ", line)
                print(" HGsamples=", hg_bin[0])
                for line in hg_bin[1:]:
                    print("           ", line)
                _write_sample_block(logf, "adc={} LGsamples= ".format(ch), lg)
                _write_sample_block(logf, "adc={} HGsamples= ".format(ch), hg)
            print(" *********************************************************************************************************************************************")

        if nevnt % 50 == 0:
            elapsed = (time.time() - start) / 3600.0
            err_msg = "   errors= {}".format(ERR) if pattern is not None else ""
            print(
                " nevnt=", nevnt, err_msg,
                "  time=" + time.strftime("%c"),
                "  elapsed=", "%.3f" % elapsed, "hrs",
            )
            logf.write(
                " nevnt=%d   errors=%s    elapsed=%.3f hrs\n"
                % (nevnt, ERR if pattern is not None else "-", elapsed)
            )
            logf.flush()


def main():
    args = parse_args()

    ppr_ip = args.ppripaddress if args.ppripaddress else DEFAULT_PPR_IP
    host_ip = args.hostipaddress if args.hostipaddress else DEFAULT_HOST_IP
    if args.ppripaddress is None:
        print("No PPr ipaddress... defaulting to", ppr_ip, "...")
    if args.hostipaddress is None:
        print("No host ipaddress... defaulting to", host_ip, "...")

    print("Communicating with PPREmu")
    ipbus = IPbus(host_ip, ppr_ip)
    print("Connected to PPr with ip:", ppr_ip, " FW version:", hex(ipbus.ReadVal(PPrReg.RO_FIRMWARE_VERSION)))

    start = time.time()
    pattern = None
    if args.pattern is None:
        print(" No pattern selected...")
    else:
        pattern = format_number(args.pattern)
        print("Pattern:", args.pattern, "selected...")
        print("Setting cfb_mb_adc_config to 0x0...")
        ipbus.DB_Write_Val(md, 0, cfb_mb_adc_config, 0, 0)
        time.sleep(0.1)
        set_adc_pattern(ipbus, md, pattern)

    if not args.adc_config_driver:
        print("No adc config driver reset issued...")
    else:
        the_value = (1 << 9) | (1 << 7) | (the_strobe_lenght << the_strobe_lenght_pos)
        print("*** Resseting adc_config_driver...")
        pulse_strobe(ipbus, md, the_value)
        time.sleep(1)
        print("*** Done resetting adc_config_driver...")

    if not args.adc_readout_reset:
        print("No ADC Readout reset issued...")
    else:
        print("Resseting ADC Readout Module...")
        time.sleep(1)
        the_value = (1 << 7) | (the_strobe_lenght << the_strobe_lenght_pos)
        pulse_strobe(ipbus, md, the_value)
        time.sleep(1)

    if not args.show_readout:
        print("To see the ADC Readout use '-s' ...")
    else:
        with open("kja.txt", "w") as logf:
            show_adc_readout(ipbus, md, pattern, start, logf)

    print("DONE put back to parallel mode ")

    if not args.reset:
        print("No reset issued!")
    else:
        reset_adcs(ipbus, md, args.adc_readout_reset)

    print("Done!")


if __name__ == "__main__":
    main()
