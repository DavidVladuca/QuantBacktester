package com.quant;

import org.zeromq.ZMQ;
import org.zeromq.ZContext;
import org.zeromq.SocketType;
import com.google.gson.Gson;

import java.util.Map; 
import java.util.HashMap; 
import java.util.concurrent.BlockingQueue; 
import java.util.concurrent.LinkedBlockingQueue; 

public class Main {

    public static class OrderSignal {
        String signal;
        double price;
        String symbol;
        double allocation;
    }

    public static class MarketEvent {
        private String type;
        private String symbol;
        private long timestamp; 
        private double price;
        private double high; 
        private double low;
        private double volume; 
        
        // 🚨 NEW: Quote Data for the Gatekeeper & OBI Flow
        private double bid_price;
        private double ask_price;
        private double bid_size;
        private double ask_size;

        // Updated Constructor
        public MarketEvent(String type, String symbol, long timestamp, double price, double high, double low, double volume, double bid_price, double ask_price, double bid_size, double ask_size) {
            this.type = type;
            this.symbol = symbol;
            this.timestamp = timestamp;
            this.price = price;
            this.high = high;
            this.low = low;
            this.volume = volume;
            this.bid_price = bid_price;
            this.ask_price = ask_price;
            this.bid_size = bid_size;
            this.ask_size = ask_size;
        }

        public String getType() { return type; }
        public String getSymbol() { return symbol; }
        public long getTimestamp() { return timestamp; }
        public double getPrice() { return price; }
        public double getHigh() { return high; }
        public double getLow() { return low; }
        public double getVolume() { return volume; }
    }

    public static void main(String[] args) {
        // 🚨 ROUTE CONSOLE OUTPUT TO FILE
        try {
            java.io.PrintStream logFile = new java.io.PrintStream(new java.io.FileOutputStream("engine_log.txt"));
            System.setOut(logFile);
            System.setErr(logFile);
            System.out.println(">>> LOGGING INITIATED: " + new java.util.Date());
        } catch (java.io.FileNotFoundException e) {
            e.printStackTrace();
        }

        boolean IS_BACKTEST_MODE = true; 
        
        String[] csvFiles = {
            "data/NVDA_macro_1min.csv",
            "data/SMH_macro_1min.csv",
            "data/NVDA_micro_2day.csv",
            "data/SMH_micro_2day.csv"
        };
        
        String[] tickers = {"NVDA", "SMH"};
        Gson gson = new Gson();
        
        Portfolio portfolio = new Portfolio(10000.0);
        ExecutionGateway gateway = IS_BACKTEST_MODE ? new SimulatedGateway() : new AlpacaGateway();

        Map<String, Double> finalPrices = new HashMap<>(); 
        Map<String, Double> beginningPrices = new HashMap<>();
        BlockingQueue<MarketEvent> eventQueue = new LinkedBlockingQueue<>();
        
        // 🚨 Flag to detect the switch from Macro to Micro
        boolean transitionedToMicro = false;

        System.out.println("Booting Engine: Connecting to Strategy...");

        try (ZContext context = new ZContext()) {
            ZMQ.Socket socket = context.createSocket(SocketType.REQ);
            socket.connect("tcp://localhost:5555");
            socket.setReceiveTimeOut(IS_BACKTEST_MODE ? 5000 : 2000); 

            // Initialize hydration state
            boolean isHydrating = true; // Start as true even in backtest to warm up Z-Score
            
            if (IS_BACKTEST_MODE) {
                System.out.println("Initiating Pure CSV Backtest Run...");
                CSVStreamer csvStreamer = new CSVStreamer(eventQueue, csvFiles);
                new Thread(() -> csvStreamer.start()).start();
            } else {
                System.out.println("Initiating Live Feed Warmup Hydration...");
                int barsPerStock = 100;
                AlpacaRESTFetcher hydrator = new AlpacaRESTFetcher(eventQueue, tickers, tickers.length * barsPerStock);
                new Thread(() -> hydrator.start()).start();
            }

            long totalLatencyMicros = 0;
            long maxLatencyMicros = 0;
            long eventCount = 0;

            while (true) { 
                MarketEvent event = eventQueue.take(); 
                
                if ("END_OF_STREAM".equals(event.getType())) {
                    System.out.println("\n=== ENGINE SHUTDOWN ===");
                    portfolio.printSummary(beginningPrices, finalPrices);
                    break; 
                }

                // 🚨 THE TRANSITION LOGIC
                // If we see bid_price > 0, we've hit the Micro Ticks.
                if (!transitionedToMicro && event.bid_price > 0) {
                    transitionedToMicro = true;
                    isHydrating = false; // Stop "hydrating", start trading
                    beginningPrices.clear(); // RESET the benchmark to current prices
                    System.out.println("\n>>> MICRO TRADING WINDOW DETECTED: Resetting Benchmark Prices...");
                }
                
                // Track beginning prices for the current active window
                if (!beginningPrices.containsKey(event.getSymbol())) {
                    beginningPrices.put(event.getSymbol(), event.getPrice());
                }
                
                finalPrices.put(event.getSymbol(), event.getPrice()); 
                portfolio.updateMarketPrice(event.getSymbol(), event.getPrice());

                String jsonPayload = gson.toJson(event);
                long startTime = System.nanoTime();

                socket.send(jsonPayload);
                String response = socket.recvStr();

                long endTime = System.nanoTime();
                long latencyMicros = (endTime - startTime) / 1000;

                if (response == null) {
                    System.out.println("WARNING: Strategy is offline. Rebuilding ZMQ Socket...");
                    socket.close();
                    socket = context.createSocket(SocketType.REQ);
                    socket.connect("tcp://localhost:5555");
                    socket.setReceiveTimeOut(IS_BACKTEST_MODE ? 5000 : 1000); 
                    Thread.sleep(1000);
                    continue;
                } else {
                    eventCount++;
                    totalLatencyMicros += latencyMicros;
                    maxLatencyMicros = Math.max(maxLatencyMicros, latencyMicros);

                    // --- THE TELEMETRY PRINT ---
                    int printInterval = IS_BACKTEST_MODE ? 50000 : 10;
                    if (!isHydrating && eventCount % printInterval == 0) { 
                        System.out.println("Events Processed: " + eventCount + " | Avg Latency: " + (totalLatencyMicros / eventCount) + " µs"); 
                    }

                    // Only process signals if we are past the hydration/macro phase
                    if (!isHydrating) {
                        OrderSignal os = gson.fromJson(response, OrderSignal.class);
                        if (os.signal != null && !os.signal.equals("HOLD")) {
                            Order newOrder = portfolio.createOrder(os.signal, os.price, os.symbol, 1.0);
                            if (newOrder != null) { 
                                gateway.execute(newOrder, event); 
                                portfolio.applyFill(newOrder); 
                            } 
                        }
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}