import time
import plotext as tplt
from db_ppr_ipbus import *

# -------------------------------
# Connection
# -------------------------------
HostIPaddressServer = "192.168.0.201"
PPrIPaddressServer = "192.168.0.2"

print(f"Connecting to PPr @ {PPrIPaddressServer}")
ipbus = IPbus(HostIPaddressServer, PPrIPaddressServer)
ppr = PPr(ipbus.ipbus)
feb = FEB(ppr)  # create FEB instance

# -------------------------------
# Test Integrator Functions
# -------------------------------
def test_integrator_DACs_and_reads(charge_values=[0], MDbroadcast=1, MDsel=None, dbside=0, verbose=True):
    print("\nStarting Integrator DAC + Read test...\n")
    
    for charge in charge_values:
        print(f"Setting DAC charge: {charge}")
        
        # Set DACs
        success = feb.set_FEB_integrator_DACs(
            charge=charge
        )
        
        # Small delay to allow integrator to settle
        time.sleep(0.1)
        
        # Reset FIFO before reading
        ppr.reset_integrator_fifo()
        
        # Read integrator values for all MD channels
        print("Reading integrator values:")
        MDmin, MDmax = (0, 4) if MDbroadcast == 1 else (0, len(MDsel))
        mdidx = 0
        for md in range(MDmin, MDmax):
            if (MDbroadcast == 1) or (MDsel and MDsel[mdidx] == 1):
                for adc in range(12):
                    value = ppr.get_data_integrator(md, adc)[0]
                    print(f"  MD {md} FEB {adc} Integrator Value: {value}")
            mdidx += 1
        
        print(f"DAC charge {charge} test {'PASSED' if success else 'FAILED'}\n")
        time.sleep(0.5)


def test_integrator_linearity(nb_steps=10, step_length_DAC=1.0, step_events=5, debug=False,
                              MDbroadcast=1, MDsel=None, dbside=0):
    """
    Perform a DAC scan to check integrator linearity using pprclass.
    Follows the Java integrator scan method. FEB object is passed explicitly.
    """
    min_val_Integrator = 0.
    max_val_Integrator = 65535.
    step_length_DAC = (max_val_Integrator - min_val_Integrator) / nb_steps

    dac_values = []
    integrator_max_values = []

    print("==> Starting Integrator Linearity Scan...")

    # -------------------------
    # Global setup
    # -------------------------
    print("Setting TTC internal...")
    ret = ppr.set_global_TTC_internal()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Resetting CRC counters...")
    # ret = ppr.reset_CRC_counters()
    # print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Setting global trigger deadtime bit...")
    ret = ppr.set_global_trigger_deadtime(0)
    print(f"  Set bit 0: {'Ok' if ret else 'Fail'}")
    ret = ppr.set_global_trigger_deadtime(1)
    print(f"  Set bit 1: {'Ok' if ret else 'Fail'}")

    print("Configuring FEB ADC bias offsets...")
    ret = feb.set_FEB_ADC_bias_offsets_DACs()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Loading FEB ADC DACs...")
    ret = feb.set_FEB_load_ADC_DACs()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Setting FEB switches...")
    ret = feb.set_FEB_switches()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Setting CIS on minidrawers...")
    ret = feb.set_CIS_Integrator_BCID_settings()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Configuring integrator readout frequency...")
    readout_frequency = 112  # in orbit units (90 us)
    ret = feb.async_write(0x115, readout_frequency)
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Internal TTC mode for BCRs...")
    ret = ppr.write(0x4, 0)
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Configuring FENICS card switches...")
    ret = feb.set_integrator_switches()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    # -------------------------
    # Loop over DAC steps
    # -------------------------
    for step in range(nb_steps + 1):
        charge_DAC = step * step_length_DAC
        dac_values.append(charge_DAC)

        print(f"Step {step+1}: DAC = {charge_DAC:.1f}")
        ret = feb.set_FEB_integrator_DACs(charge=int(charge_DAC))
        ppr.reset_integrator_fifo()
        print(f"  DAC set result: {'Ok' if ret else 'Failed'}")

        # Track max per MD/ADC like Java
        max_values_step = []

        for event in range(step_events):
            for md in range(4):
                for adc in range(12):
                    data = ppr.get_data_integrator(md, adc, 1)
                    if data:
                        max_val = max(data)
                        max_values_step.append(max_val)
                        if debug and adc == 0:
                            print(f"    MD {md} ADC {adc}: first={data[0]}, max={max_val}")

            time.sleep(0.05)  # mimic per-event delay

        # Average max value for this DAC step
        avg_max = sum(max_values_step) / len(max_values_step) if max_values_step else 0
        integrator_max_values.append(avg_max)
        print(f"  Step {step+1} average max integrator value: {avg_max:.1f}")

    # -------------------------
    # Plot results
    # -------------------------
    tplt.clear_figure()
    tplt.plot(dac_values, integrator_max_values, marker="dot", label="Integrator Max")
    tplt.title("Integrator Linearity Scan")
    tplt.xlabel("DAC Value")
    tplt.ylabel("Max Integrator Value")
    tplt.grid(True)
    tplt.show()

    print("Integrator linearity scan completed.")



def test_integrator_lin_per_channel(nb_steps=10, step_events=1, debug=False):

    """
    DAC scan per channel, plotting 12 ADCs per MD in a 2x6 grid,
    and printing integrator values per DAC step in the console.
    """
    import plotext as plt

    min_val = 0.
    max_val = 4095.
    step_length_DAC = (max_val - min_val) / nb_steps
    dac_values = [step * step_length_DAC for step in range(nb_steps)]

    # Store results per channel
    results = {(md, adc): [] for md in range(4) for adc in range(12)}

    print("==> Starting Integrator Linearity Scan...")

    # -------------------------
    # Global setup
    # -------------------------
    print("Setting TTC internal... ", end ="")
    ret = ppr.set_global_TTC_internal()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    # print("Resetting CRC counters...")
    # ret = ppr.reset_CRC_counters()
    # print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Setting global trigger deadtime bit...")
    ret = ppr.set_global_trigger_deadtime(0)
    print(f"  Set bit 0: {'Ok' if ret else 'Fail'}")
    ret = ppr.set_global_trigger_deadtime(1)
    print(f"  Set bit 1: {'Ok' if ret else 'Fail'}")

    print("Configuring FEB ADC bias offsets... ", end ="")
    ret = feb.set_FEB_ADC_bias_offsets_DACs()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Loading FEB ADC DACs... ", end ="")
    ret = feb.set_FEB_load_ADC_DACs()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Setting FEB switches... ", end ="")
    ret = feb.set_FEB_switches()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Setting CIS on minidrawers... ", end ="")
    ret = feb.set_CIS_Integrator_BCID_settings()
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Configuring integrator readout frequency... ", end ="")
    readout_frequency = 112  # in orbit units (90 us)
    ret = feb.async_write(None, 0x115, readout_frequency)
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Internal TTC mode for BCRs... ", end ="")
    ret = ppr.write(0x4, 0)
    print(f"  Result: {'Ok' if ret else 'Failed'}")

    print("Configuring FENICS card switches... ", end ="")
    ret = feb.set_integrator_switches()
    print(f"  Result: {'Ok' if ret else 'Failed'}")
    
    print("Configuring Integrator DACs to 0... ", end ="")
    ret = feb.set_FEB_integrator_DACs(charge=int(0))
    ppr.reset_integrator_fifo()
    print(f"  Result: {'Ok' if ret else 'Failed'}")
    time.sleep(0.2)

    # Loop over DAC steps
    for dac_value in dac_values:
        ret = feb.set_FEB_integrator_DACs(charge=int(dac_value))
        ppr.reset_integrator_fifo()
        time.sleep(0.2)
        for md in range(4):
            for adc in range(12):
                max_vals = []
                for event in range(step_events):
                    data = ppr.get_data_integrator(md, adc, 1)
                    if data:
                        max_vals.append(max(data))
                avg_max = sum(max_vals)/len(max_vals) if max_vals else 0
                results[(md, adc)].append(avg_max)

    # -------------------------
    # Print data per MD
    # -------------------------
    for md in range(4):
        print(f"\n=== MD {md} Integrator Data ===")
        header = "DAC".ljust(8) + "".join([f"ADC{adc}".rjust(10) for adc in range(12)])
        print(header)
        print("-" * len(header))
        for step_idx, dac_value in enumerate(dac_values):
            row = f"{int(dac_value):<8}"
            for adc in range(12):
                val = results[(md, adc)][step_idx]
                row += f"{val:>10.1f}"
            print(row)

    # -------------------------
    # Plot per MD as grid
    # -------------------------
    for md in range(4):
        print(f"\n=== Plotting MD {md+1} ===\n")
        plt.clear_figure()
        plt.plotsize(100, 30)   # 👈 control size (width, height in characters)

        plt.subplots(2, 6)  # 2 rows, 6 cols for 12 ADCs
        for adc in range(12):
            row = (adc // 6) + 1
            col = (adc % 6) + 1
            plt.subplot(row, col)
            plt.scatter(dac_values, results[(md, adc)], marker="dot")
            # --- FIX AXIS RANGE HERE ---
            plt.xlim(0, 4095)  # Replace with your desired DAC range
            plt.ylim(0, 65335)  # Replace with your desired Max range
            plt.title(f"ADC {adc}")
            plt.xlabel("DAC")
            plt.ylabel("Max")
        plt.show()

    print("Per-MD grid integrator linearity scan completed.")
    
    
        
# -------------------------------
# Run the test
# -------------------------------
if __name__ == "__main__":
    test_integrator_lin_per_channel()
    # test_integrator_scan()
    # test_integrator_DACs_and_reads(charge_values=[0, 1000, 2000], MDbroadcast=1, MDsel=[1,1,1,1])