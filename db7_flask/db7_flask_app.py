#!/usr/bin/env python3
"""Flask front-end for daughterboard register R/W.

Uses the same IPbus methods as db7_modregval.py:
  IPbus(controlhub_ip, ppr_ip)
  DB_Read_Val / DB_Write_Val / SyncWrite / SyncClear / ReadVal

Register numbers come from vhdl/db6_design_package.vhd via db_lib.py.
"""
from __future__ import print_function

import os
import sys
import threading
import traceback

from flask import Flask, jsonify, render_template, request

HERE = os.path.dirname(os.path.abspath(__file__))
TILE_SCRIPTS = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if TILE_SCRIPTS not in sys.path:
    sys.path.append(TILE_SCRIPTS)

from db_lib import (  # noqa: E402
    REGS_BY_BUS,
    decode_fields,
    decode_value,
    find_register,
    format_number,
    public_register_map,
)
from db_ppr_ipbus import IPbus    # noqa: E402

DEFAULT_CONTROLHUB_IP = "192.168.0.201"
DEFAULT_PPR_IP = "192.168.0.3"

# db7_modregval.py FPGA encoding: A -> 2, B -> 3, else broadcast 0
FPGA_CODE = {"A": 2, "B": 3, "a": 2, "b": 3, "broadcast": 0, "": 0}

app = Flask(
    __name__,
    template_folder=os.path.join(HERE, "templates"),
    static_folder=os.path.join(HERE, "static"),
)

_lock = threading.Lock()
_state = {
    "ppr": None,
    "controlhub_ip": DEFAULT_CONTROLHUB_IP,
    "ppr_ip": DEFAULT_PPR_IP,
    "fw_version": None,
    "error": None,
}


def _as_int(val):
    if val is None:
        return 0
    if isinstance(val, (list, tuple)):
        if not val:
            return 0
        return _as_int(val[0])
    return int(val) & 0xFFFFFFFF


def _parse_number(text, default=None):
    if text is None or text == "":
        return default
    if isinstance(text, (int, float)):
        return int(text)
    return format_number(str(text).strip())


def _fpga_code(spec):
    if spec is None or spec == "":
        return 0
    if isinstance(spec, int):
        return spec
    key = str(spec).strip()
    if key in FPGA_CODE:
        return FPGA_CODE[key]
    try:
        return int(key, 0)
    except ValueError:
        return 0


def _md_index(md):
    """UI minidrawer is 1..4; IPbus uses 0..3 (db7_modregval.py)."""
    md = int(md)
    if md >= 1:
        return md - 1
    return md


def _require_ppr():
    ppr = _state["ppr"]
    if ppr is None:
        raise RuntimeError("Not connected. Set ControlHub / TilePPr IP and connect.")
    return ppr


def _fmt_side(value):
    value = _as_int(value)
    return {
        "raw": value,
        "hex": "0x{:08X}".format(value),
        "dec": value,
        "bin": "0b{:032b}".format(value),
    }


def _pack_read(reg, rbk):
    side_a = _as_int(rbk[0] if rbk else 0)
    side_b = _as_int(rbk[1] if rbk and len(rbk) > 1 else 0)
    return {
        "register": {
            "index": reg["index"],
            "name": reg["name"],
            "hw_addr": reg["hw_addr"],
            "hw_addr_hex": "0x{:03X}".format(reg["hw_addr"]),
            "bus": reg.get("bus"),
            "writable": bool(reg.get("writable")),
            "note": reg.get("note") or "",
        },
        "side_a": _fmt_side(side_a),
        "side_b": _fmt_side(side_b),
        "fields_a": decode_fields(reg, side_a),
        "fields_b": decode_fields(reg, side_b),
        "decoded_a": decode_value(reg, side_a),
        "decoded_b": decode_value(reg, side_b),
    }


@app.route("/")
def index():
    return render_template(
        "db7_reg.html",
        default_controlhub_ip=DEFAULT_CONTROLHUB_IP,
        default_ppr_ip=DEFAULT_PPR_IP,
    )


@app.route("/api/registers")
def api_registers():
    return jsonify(public_register_map())


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify({
            "connected": _state["ppr"] is not None,
            "controlhub_ip": _state["controlhub_ip"],
            "ppr_ip": _state["ppr_ip"],
            "fw_version": _state["fw_version"],
            "fw_version_hex": (
                None if _state["fw_version"] is None
                else "0x{:08X}".format(_state["fw_version"])
            ),
            "error": _state["error"],
        })


@app.route("/api/connect", methods=["POST"])
def api_connect():
    body = request.get_json(silent=True) or {}
    controlhub_ip = (body.get("controlhub_ip") or DEFAULT_CONTROLHUB_IP).strip()
    ppr_ip = (body.get("ppr_ip") or DEFAULT_PPR_IP).strip()
    verbose = bool(body.get("verbose"))

    with _lock:
        try:
            ppr = IPbus(controlhub_ip, ppr_ip, verbose=verbose)
            fw = _as_int(ppr.ReadVal(1))
            _state["ppr"] = ppr
            _state["controlhub_ip"] = controlhub_ip
            _state["ppr_ip"] = ppr_ip
            _state["fw_version"] = fw
            _state["error"] = None
            return jsonify({
                "ok": True,
                "controlhub_ip": controlhub_ip,
                "ppr_ip": ppr_ip,
                "fw_version": fw,
                "fw_version_hex": "0x{:08X}".format(fw),
            })
        except Exception as exc:
            _state["ppr"] = None
            _state["fw_version"] = None
            _state["error"] = str(exc)
            return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    with _lock:
        _state["ppr"] = None
        _state["fw_version"] = None
        _state["error"] = None
    return jsonify({"ok": True})


@app.route("/api/sync_clear", methods=["POST"])
def api_sync_clear():
    with _lock:
        try:
            ppr = _require_ppr()
            ppr.SyncClear()
            return jsonify({"ok": True})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(exc)}), 500


def _read_one(ppr, md, bus, spec):
    reg = find_register(bus, spec)
    if reg is None:
        raise ValueError("Unknown register: {!r}".format(spec))
    rbk = ppr.DB_Read_Val(md, reg["hw_addr"])
    return _pack_read(reg, rbk)


@app.route("/api/read", methods=["POST"])
def api_read():
    body = request.get_json(silent=True) or {}
    md = _md_index(body.get("md", 1))
    bus = (body.get("bus") or "rx").lower()
    spec = body.get("register")
    if spec is None:
        spec = body.get("index")
    with _lock:
        try:
            ppr = _require_ppr()
            result = _read_one(ppr, md, bus, spec)
            result["ok"] = True
            result["md"] = md + 1
            return jsonify(result)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/read_all", methods=["POST"])
def api_read_all():
    body = request.get_json(silent=True) or {}
    md = _md_index(body.get("md", 1))
    bus = (body.get("bus") or "rx").lower()
    regs = REGS_BY_BUS.get(bus)
    if not regs:
        return jsonify({"ok": False, "error": "Unknown bus {!r}".format(bus)}), 400
    with _lock:
        try:
            ppr = _require_ppr()
            rows = []
            for reg in regs:
                rbk = ppr.DB_Read_Val(md, reg["hw_addr"])
                rows.append(_pack_read(reg, rbk))
            return jsonify({"ok": True, "md": md + 1, "bus": bus, "rows": rows})
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/write", methods=["POST"])
def api_write():
    """Async (default) or sync write, matching db7_modregval.py."""
    body = request.get_json(silent=True) or {}
    md = _md_index(body.get("md", 1))
    fpga = _fpga_code(body.get("fpga"))
    bus = (body.get("bus") or "rx").lower()
    spec = body.get("register")
    if spec is None:
        spec = body.get("index")

    try:
        value = _parse_number(body.get("value"))
        if value is None:
            raise ValueError("Missing write value")
        mask = _parse_number(body.get("mask"), 0) or 0
        aim = body.get("aim")
        if aim not in (None, ""):
            value = value << _parse_number(aim, 0)
        sync = bool(body.get("sync"))
        bcid = _parse_number(body.get("bcid")) if sync else None
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    reg = find_register(bus, spec)
    if reg is None:
        return jsonify({"ok": False, "error": "Unknown register"}), 400

    write_index = reg["index"]
    with _lock:
        try:
            ppr = _require_ppr()
            if sync:
                if bcid is None:
                    raise ValueError("Sync write needs a BCID")
                # Same call as db7_modregval.py, but address the selected register
                # (the CLI hard-codes dba=0).
                ppr.SyncWrite(bcid, (fpga << 12) + write_index, value)
            else:
                ppr.DB_Write_Val(md, fpga, write_index, value, mask)

            result = _read_one(ppr, md, bus, spec)
            result["ok"] = True
            result["md"] = md + 1
            result["fpga"] = fpga
            result["wrote"] = {
                "index": write_index,
                "value": value,
                "value_hex": "0x{:08X}".format(value & 0xFFFFFFFF),
                "mask": mask,
                "mask_hex": "0x{:08X}".format(mask & 0xFFFFFFFF if mask else 0xFFFFFFFF),
                "sync": sync,
                "bcid": bcid,
            }
            return jsonify(result)
        except (RuntimeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            traceback.print_exc()
            return jsonify({"ok": False, "error": str(exc)}), 500


def main():
    global DEFAULT_CONTROLHUB_IP, DEFAULT_PPR_IP
    import argparse
    parser = argparse.ArgumentParser(description="DB7 register Flask UI")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--controlhub", default=DEFAULT_CONTROLHUB_IP,
                        help="Default ControlHub IP shown in the UI")
    parser.add_argument("--ppr", default=DEFAULT_PPR_IP,
                        help="Default TilePPr IP shown in the UI")
    args = parser.parse_args()
    DEFAULT_CONTROLHUB_IP = args.controlhub
    DEFAULT_PPR_IP = args.ppr
    _state["controlhub_ip"] = args.controlhub
    _state["ppr_ip"] = args.ppr
    print("DB7 register UI  http://{}:{}/".format(
        "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host,
        args.port,
    ))
    print("  ControlHub default:", args.controlhub)
    print("  TilePPr default:   ", args.ppr)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
