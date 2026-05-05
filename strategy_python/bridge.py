import zmq
import json
import time

from ensemble_active.strategy_ensemble import MasterEnsemble # or your trading bot

def start_strategy(strategy_class):
    # setup (REP = Reply, Listen on port 5555)
    context = zmq.Context()
    socket = context.socket(zmq.REP) 
    socket.bind("tcp://*:5555")

    # 1 second timeout on the socket
    socket.setsockopt(zmq.RCVTIMEO, 1000)

    print(f"Python Bridge listening on port 5555... (Press Ctrl+C to stop)")
    print(f"Active Strategy: {strategy_class.__name__} (GLOBAL INSTANCE)")

    master_bot = strategy_class()
    while True:
        try:
            message = socket.recv_string()
            try:
                event = json.loads(message)
            except json.JSONDecodeError as e:
                print(f"[BRIDGE] Malformed JSON from engine: {e}")
                socket.send_string(json.dumps({"status": "ERROR", "reason": "bad JSON"}))
                continue

            try:
                if event.get("type") == "MARKET_DATA":
                    response_dict = master_bot.process_event(event)
                    if response_dict:
                        socket.send_string(json.dumps(response_dict))
                    else:
                        socket.send_string(json.dumps({"status": "ACK"}))
                else:
                    socket.send_string(json.dumps({"status": "ACK"}))
            except Exception as e:
                print(f"[BRIDGE] Strategy error: {e}")
                socket.send_string(json.dumps({"status": "ERROR", "reason": str(e)}))

        except zmq.Again:
            pass
        except KeyboardInterrupt:
            print("\nStopping script...")
            break

if __name__ == "__main__":    
    active_bot = MasterEnsemble
    start_strategy(active_bot)