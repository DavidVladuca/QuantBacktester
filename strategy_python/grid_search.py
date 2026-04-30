import json
import subprocess
import time
import re
import os

# --- 1. SURGICAL CONFIGURATION ---
# We locked the safest parameters from your last run
# to focus processing power on testing the new Regime logic.
z_score_options = [2.5, 3.0]
momentum_options = [3.0, 3.5]
obi_options = [0.4]  # Locked to 0.4
regime_options = [0.5, 1.0, 1.5] # 🚨 NEW: The Volatility Thresholds

total_runs = len(z_score_options) * len(momentum_options) * len(obi_options) * len(regime_options)

# --- 2. PATHS (Absolute for Reliability) ---
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")
results_path = os.path.join(script_dir, "grid_search_results_v2.csv") # Saved as v2
java_dir = os.path.join(script_dir, "..", "backend_java", "backtester")
log_path = os.path.join(java_dir, "engine_log.txt")

# --- 3. COMMANDS ---
python_cmd = ["python", "bridge.py"]
java_cmd = 'mvn compile exec:java "-Dexec.mainClass=com.quant.Main"'

print(f"🚀 SURGICAL GRID SEARCH STARTING: {total_runs} Runs")

with open(results_path, "w") as rf:
    # 🚨 Added Regime to the CSV headers
    rf.write("Z,Mom,OBI,Regime,PnL,Return\n")

    for z in z_score_options:
        for mom in momentum_options:
            for obi in obi_options:
                for reg in regime_options: # 🚨 NEW 4TH LOOP
                    print(f"\n--- RUNNING: Z={z} | Mom={mom} | OBI={obi} | Regime={reg} ---")
                    
                    # Update Config with the new Regime Threshold
                    with open(config_path, "w") as f:
                        json.dump({
                            "z_score_threshold": z, 
                            "momentum_threshold": mom, 
                            "obi_threshold": obi,
                            "regime_threshold": reg
                        }, f)
                    
                    # Start Bridge
                    bridge = subprocess.Popen(python_cmd, cwd=script_dir)
                    time.sleep(3)
                    
                    # Start Java 
                    print("Running Java Engine...")
                    subprocess.run(java_cmd, cwd=java_dir, shell=True)
                    
                    # Stop Bridge
                    bridge.terminate()
                    bridge.wait()

                    # Extract Results (Reading only the Tail of the log for speed/accuracy)
                    if os.path.exists(log_path):
                        with open(log_path, "rb") as f:
                            f.seek(0, os.SEEK_END)
                            f.seek(max(0, f.tell() - 2000))
                            tail = f.read().decode('utf-8', errors='ignore')
                            
                            pnl = re.search(r"Total Profit/Loss:\s*\$([-]?\d+\.\d+)", tail)
                            ret = re.search(r"Bot Total Return:\s*([-]?\d+\.\d+)%", tail)
                            
                            pnl_val = pnl.group(1) if pnl else "N/A"
                            ret_val = ret.group(1) if ret else "N/A"
                            
                            print(f"✅ FINISHED | PnL: ${pnl_val} | Return: {ret_val}%")
                            rf.write(f"{z},{mom},{obi},{reg},{pnl_val},{ret_val}\n")
                            rf.flush()
                    else:
                        print("❌ Error: Log file not found!")

print("\n🎉 ALL RUNS COMPLETE. Check grid_search_results_v2.csv")