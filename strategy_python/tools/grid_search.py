import json
import subprocess
import time
import re
import socket

z_score_options = [1.25, 1.5, 1.75, 2.0]
momentum_options = [0.5, 0.7, 0.9, 1.1, 1.3]
obi_options = [0.0]  # currently unused
regime_options = [0.04, 0.06, 0.08, 0.10, 0.12]
entry_thresh_options = [0.25, 0.30, 0.35, 0.40]

total_runs = (len(z_score_options) * len(momentum_options) *
              len(obi_options) * len(regime_options) * len(entry_thresh_options))

# paths
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
STRATEGY_DIR = TOOLS_DIR.parent
ROOT_DIR = STRATEGY_DIR.parent

config_path = STRATEGY_DIR / "config.json"
results_path = TOOLS_DIR / "grid_search_results.csv"
java_dir = ROOT_DIR / "backend_java" / "backtester"

# commands
python_cmd = ["python", "bridge.py"]
java_cmd = 'mvn exec:java "-Dexec.mainClass=com.quant.Main"' 

print(f"GRID SEARCH STARTING: {total_runs} Runs")

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

                    # start bridge.py
                    bridge = subprocess.Popen(python_cmd, cwd=STRATEGY_DIR)

                    # poll until the bridge is accepting connections instead of sleeping
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
                        print("(Error) Bridge failed to start within 15s. Skipping run.")
                        bridge.terminate()
                        bridge.wait()
                        rf.write(f"{z},{mom},{obi},{reg},{entry_thresh},N/A,N/A\n")
                        rf.flush()
                        continue
                    
                    # start Main.java
                    print("Running Java Engine...")
                    
                    result = subprocess.run(java_cmd, cwd=java_dir, shell=True, capture_output=True, text=True)                    
                    # stop bridge.py
                    bridge.terminate()
                    bridge.wait()

                    # get results from engine_log.txt
                    engine_log_path = java_dir / "engine_log.txt"

                    if engine_log_path.exists():
                        with open(engine_log_path, "r", encoding="utf-8", errors="ignore") as lf:
                            java_output = lf.read()
                    else:
                        java_output = result.stdout
                    
                    # search the output string directly
                    pnl = re.search(r"Total Profit/Loss:\s*\$([-]?\d+\.\d+)", java_output)
                    ret = re.search(r"Bot Total Return:\s*([-]?\d+\.\d+)%", java_output)
                    
                    pnl_val = pnl.group(1) if pnl else "N/A"
                    ret_val = ret.group(1) if ret else "N/A"
                    
                    print(f"=> FINISHED | PnL: ${pnl_val} | Return: {ret_val}%")
                    rf.write(f"{z},{mom},{obi},{reg},{entry_thresh},{pnl_val},{ret_val}\n")
                    rf.flush()
                    
                    # safety check -> if N/A, print the last few lines of the output so we can see why it failed
                    if pnl_val == "N/A":
                        print("(Error) Failed to parse output. Last 5 lines of Java Console:")
                        lines = java_output.strip().split('\n')
                        for line in lines[-5:]:
                            print("   " + line)

print("\n(Done) ALL RUNS COMPLETE. Check grid_search_results.csv")