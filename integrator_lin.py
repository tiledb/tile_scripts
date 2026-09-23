#!/usr/bin/env python3

import time
import Herakles
from db_ppr_ipbus import PPr, FEB
import plotext as tplt


# ------------------ FIT ------------------

def linear_fit(x, y):
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n

    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den = sum((x[i] - mean_x) ** 2 for i in range(n))

    slope = num / den if den != 0 else 0
    intercept = mean_y - slope * mean_x

    y_fit = [slope * xi + intercept for xi in x]

    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    ss_res = sum((y[i] - y_fit[i]) ** 2 for i in range(n))
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    max_dev = max(abs(y[i] - y_fit[i]) for i in range(n))

    return slope, intercept, r2, max_dev


# ------------------ CONFIG ------------------

HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

nMD = 1
nchanperMD = 12
dbside = 0

nsteps = 10
step_events = 1

min_DAC = 0
max_DAC = 4095
step_length = (max_DAC - min_DAC) / nsteps


# ------------------ CONNECT ------------------

print(f"Connecting to PPr @ {PPrIPaddressServer}")

ipbus = Herakles.Uhal(
    f"tcp://{HostIPaddressServer}:10203?target={PPrIPaddressServer}:50001"
)

ppr = PPr(ipbus)
feb = FEB(ppr)

print(f"Connected. FW version: 0x{ppr.get_firmware_version():08X}")


# ------------------ GLOBAL CONFIG ------------------

ppr.set_global_TTC_internal()
ppr.reset_CRC_counters()
ppr.set_global_trigger_deadtime(0)
ppr.set_global_trigger_deadtime(1)


# ------------------ INTEGRATOR SETUP ------------------

mds = list(range(nMD))

print("\n==> Configuring integrator...\n")
ppr.configure_integrator(feb, mds, dbside)


# ------------------ DATA STORAGE ------------------

step_x = []
avgINT = [[] for _ in range(nMD * nchanperMD)]


# ------------------ MAIN SWEEP ------------------

print("\n==> Starting integrator sweep...\n")

for step in range(nsteps + 1):

    dac = int(min_DAC + step * step_length)
    step_x.append(dac)

    print(f"[STEP {step}] DAC = {dac}")

    # --- Apply DAC to all channels ---
    ppr.set_integrator_DAC_all(feb, mds, dbside, dac)

    # --- Reset FIFO ---
    ppr.reset_integrator_fifo()

    # --- Wait for integrator accumulation ---
    time.sleep(1.0)

    # --- Read events ---
    for event in range(step_events):

        data = ppr.read_integrator_event(mds, nchanperMD, samples=1)

        for md in range(nMD):
            for ch in range(nchanperMD):

                value = data[md][ch]
                idx = md * nchanperMD + ch

                avgINT[idx].append(value)


# ------------------ RESULTS ------------------

print("\n========== LINEARITY RESULTS ==========\n")

for md in range(nMD):
    for ch in range(nchanperMD):

        idx = md * nchanperMD + ch

        slope, offset, r2, maxdev = linear_fit(step_x, avgINT[idx])

        print(f"MD{md} Ch{ch}")
        print(f"  slope = {slope:.6f}")
        print(f"  offset = {offset:.3f}")
        print(f"  R^2 = {r2:.6f}")
        print(f"  max deviation = {maxdev:.3f}")
        print()

        # -------- ASCII Plot --------
        tplt.clear_figure()
        tplt.plot(step_x, avgINT[idx])
        tplt.title(f"MD{md} Ch{ch}")
        tplt.xlabel("DAC")
        tplt.ylabel("Integrator")
        tplt.show()


print("\n✅ Integrator sweep completed.\n")