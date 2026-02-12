#!/usr/bin/env python3

import argparse
import sys
from db_ppr_ipbus import IPbus   # <-- change this import

# -------------------------------------------------
# Defaults
# -------------------------------------------------
DEFAULT_PPR_IP = "192.168.0.2"
DEFAULT_HOST_IP = "192.168.0.201"


def get_ipbus(args):
    return IPbus(
        controlhub_ipaddress=args.hostipaddress,
        ppr_ipaddress=args.ppripaddress,
        verbose=args.verbose
    )


# -------------------------------------------------
# Command handlers
# -------------------------------------------------

def handle_sync(args):
    ipb = get_ipbus(args)

    if args.action == "clear":
        ipb.SyncClear()
    elif args.action == "reset":
        ipb.SyncRest()
    elif args.action == "enable":
        ipb.SyncEnable()
    elif args.action == "loop":
        ipb.SyncLoop(args.num)

    print("OK")


def handle_rod(args):
    ipb = get_ipbus(args)

    if args.action == "read":
        data = ipb.RODRead(args.chan, args.gain, args.num)
        print(data)

    elif args.action == "read-md":
        data = ipb.RODReadMD(
            md=args.md,
            nchan=args.nchan,
            nsamp=args.nsamp,
            stride=args.stride
        )
        for ch, samples in enumerate(data):
            print(f"CH{ch:02d}: {samples}")


def handle_reg(args):
    ipb = get_ipbus(args)

    if args.action == "read":
        val = ipb.ReadVal(args.addr)
        print(hex(val))

    elif args.action == "write":
        ipb.RODConfigWrite(args.addr, args.value)
        print("OK")


def handle_db(args):
    ipb = get_ipbus(args)

    if args.action == "read":
        val = ipb.DB_Read_Val(args.md, args.reg)
        print(val)

    elif args.action == "write":
        ipb.DB_Write_Val(args.md, args.fpga, args.reg, args.value, args.mask)
        print("OK")


def handle_deskew(args):
    ipb = get_ipbus(args)

    if args.mode == "all":
        ipb.DB_Deskew_All_Channels(args.md, args.fpga, args.phase)

    elif args.mode == "quad":
        ipb.DB_Deskew_Channels(args.md, args.fpga, args.quadrant, args.phase)

    print("OK")


# -------------------------------------------------
# Main argparse
# -------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="IPbus CLI utility",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--ppripaddress", default=DEFAULT_PPR_IP)
    parser.add_argument("--hostipaddress", default=DEFAULT_HOST_IP)
    parser.add_argument("-v", "--verbose", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---------- sync ----------
    sync = subparsers.add_parser("sync", help="Sync commands")
    sync_sub = sync.add_subparsers(dest="action", required=True)

    sync_sub.add_parser("clear")
    sync_sub.add_parser("reset")
    sync_sub.add_parser("enable")

    sync_loop = sync_sub.add_parser("loop")
    sync_loop.add_argument("num", type=int)

    sync.set_defaults(func=handle_sync)

    # ---------- rod ----------
    rod = subparsers.add_parser("rod", help="ROD operations")
    rod_sub = rod.add_subparsers(dest="action", required=True)

    rod_read = rod_sub.add_parser("read")
    rod_read.add_argument("--chan", type=int, required=True)
    rod_read.add_argument("--gain", type=int, choices=[0, 1], default=0)
    rod_read.add_argument("--num", type=int, default=16)

    rod_read_md = rod_sub.add_parser("read-md")
    rod_read_md.add_argument("--md", type=int, default=0)
    rod_read_md.add_argument("--nchan", type=int, default=12)
    rod_read_md.add_argument("--nsamp", type=int, default=16)
    rod_read_md.add_argument("--stride", type=int, default=32)

    rod.set_defaults(func=handle_rod)

    # ---------- register ----------
    reg = subparsers.add_parser("reg", help="Direct register access")
    reg_sub = reg.add_subparsers(dest="action", required=True)

    reg_read = reg_sub.add_parser("read")
    reg_read.add_argument("addr", type=lambda x: int(x, 0))

    reg_write = reg_sub.add_parser("write")
    reg_write.add_argument("addr", type=lambda x: int(x, 0))
    reg_write.add_argument("value", type=lambda x: int(x, 0))

    reg.set_defaults(func=handle_reg)

    # ---------- DB ----------
    db = subparsers.add_parser("db", help="DB operations")
    db_sub = db.add_subparsers(dest="action", required=True)

    db_read = db_sub.add_parser("read")
    db_read.add_argument("--md", type=int, required=True)
    db_read.add_argument("--reg", type=lambda x: int(x, 0), required=True)

    db_write = db_sub.add_parser("write")
    db_write.add_argument("--md", type=int, required=True)
    db_write.add_argument("--fpga", type=int, required=True)
    db_write.add_argument("--reg", type=lambda x: int(x, 0), required=True)
    db_write.add_argument("--value", type=lambda x: int(x, 0), required=True)
    db_write.add_argument("--mask", type=lambda x: int(x, 0), default=0)

    db.set_defaults(func=handle_db)

    # ---------- deskew ----------
    deskew = subparsers.add_parser("deskew", help="Deskew operations")
    deskew_sub = deskew.add_subparsers(dest="mode", required=True)

    d_all = deskew_sub.add_parser("all")
    d_all.add_argument("--md", type=int, required=True)
    d_all.add_argument("--fpga", type=int, required=True)
    d_all.add_argument("--phase", type=int, required=True)

    d_quad = deskew_sub.add_parser("quad")
    d_quad.add_argument("--md", type=int, required=True)
    d_quad.add_argument("--fpga", type=int, required=True)
    d_quad.add_argument("--quadrant", type=int, choices=[0, 1, 2], required=True)
    d_quad.add_argument("--phase", type=int, required=True)

    deskew.set_defaults(func=handle_deskew)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
