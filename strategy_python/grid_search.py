import json
import subprocess
import time
import re
import os
import socket

# z_score_options      = [1.5, 2.0, 3.0]    # Mean reversion stretch (σ deviations from rolling mean)
# momentum_options     = [0.8, 1.2, 1.8]    # Breakout threshold (random-walk-normalised return σ)
# obi_options          = [0.40, 0.55]        # Order book imbalance EMA required for full OBI confidence
# regime_options       = [0.05, 0.10, 0.15] # 1-min return std (%) to flip CHOP → TREND weighting
# entry_thresh_options = [0.35, 0.45]        # Master score gate for trade entry
z_score_options      = [3.0, 3.5]           # The surviving edge, plus an extreme test
momentum_options     = [1.5]                # LOCKED: It was a passenger at high Z-scores
obi_options          = [0.55, 0.65]         # Strict order-book support, and stricter
regime_options       = [0.05, 0.10]         # The proven NVDA volatility pockets
entry_thresh_options = [0.45, 0.50]         # The surviving gate, plus the maximum gate

total_runs = (len(z_score_options) * len(momentum_options) *
              len(obi_options) * len(regime_options) * len(entry_thresh_options))

# --- 2. PATHS ---
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")
results_path = os.path.join(script_dir, "grid_search_results_v5.csv")
java_dir = os.path.join(script_dir, "..", "backend_java", "backtester") 

# --- 3. COMMANDS ---
python_cmd = ["python", "bridge.py"]
java_cmd = 'mvn exec:java "-Dexec.mainClass=com.quant.Main"'

print(f"🚀 BOSS GRID SEARCH STARTING: {total_runs} Runs")

with open(results_path, "w") as rf:
    rf.write("Z,Mom,OBI,Regime,Entry,PnL,Return\n")

    for z in z_score_options:
        for mom in momentum_options:
            for obi in obi_options:
                for reg in regime_options:
                  for entry_thresh in entry_thresh_options:
                    print(f"\n--- RUNNING: Z={z} | Mom={mom} | OBI={obi} | Regime={reg} | Entry={entry_thresh} ---")

                    with open(config_path, "w") as f:
                        json.dump({
                            "z_score_threshold": z,
                            "momentum_threshold": mom,
                            "obi_threshold": obi,
                            "regime_threshold": reg,
                            "total_capital": 10000.0,
                            "max_risk_per_trade_pct": 0.01,
                            "commission_rate": 0.0001,
                            "slippage_rate": 0.0005,
                            "entry_threshold": entry_thresh
                        }, f, indent=4)

                    # Start Bridge
                    bridge = subprocess.Popen(python_cmd, cwd=script_dir)

                    # Poll until the bridge is accepting connections instead of sleeping blindly
                    bridge_ready = False
                    deadline = time.time() + 15
                    while time.time() < deadline:
                        try:
                            with socket.create_connection(("localhost", 5555), timeout=0.5):
                                bridge_ready = True
                                break
                        except (ConnectionRefusedError, OSError):
                            time.sleep(0.2)

                    if not bridge_ready:
                        print("❌ Bridge failed to start within 15s. Skipping run.")
                        bridge.terminate()
                        bridge.wait()
                        rf.write(f"{z},{mom},{obi},{reg},{entry_thresh},N/A,N/A\n")
                        rf.flush()
                        continue
                    
                    # Start Java AND CAPTURE ITS CONSOLE OUTPUT
                    print("Running Java Engine...")
                    
                    # 🚨 THIS IS THE FIX: Capture the stdout instead of looking for a file
                    result = subprocess.run(java_cmd, cwd=java_dir, shell=True, capture_output=True, text=True)
                    
                    # Stop Bridge
                    bridge.terminate()
                    bridge.wait()

                    # Extract Results from the captured Console Output
                    java_output = result.stdout
                    
                    # Search the output string directly
                    pnl = re.search(r"Total Profit/Loss:\s*\$([-]?\d+\.\d+)", java_output)
                    ret = re.search(r"Bot Total Return:\s*([-]?\d+\.\d+)%", java_output)
                    
                    pnl_val = pnl.group(1) if pnl else "N/A"
                    ret_val = ret.group(1) if ret else "N/A"
                    
                    print(f"✅ FINISHED | PnL: ${pnl_val} | Return: {ret_val}%")
                    rf.write(f"{z},{mom},{obi},{reg},{entry_thresh},{pnl_val},{ret_val}\n")
                    rf.flush()
                    
                    # Safety check: If it's still N/A, print the last few lines of the output so we can see why it failed
                    if pnl_val == "N/A":
                        print("❌ Failed to parse output. Last 5 lines of Java Console:")
                        lines = java_output.strip().split('\n')
                        for line in lines[-5:]:
                            print("   " + line)

print("\n🎉 ALL RUNS COMPLETE. Check grid_search_results_v5.csv")