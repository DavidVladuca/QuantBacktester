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
        double quantity;
    }

    public static class BacktestConfig {
        double commission_rate = 0.0001;
        double slippage_rate  = 0.0005;
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
        // try {
        //     java.io.PrintStream logFile = new java.io.PrintStream(new java.io.FileOutputStream("engine_log.txt"));
        //     System.setOut(logFile);
        //     System.setErr(logFile);
        //     System.out.println(">>> LOGGING INITIATED: " + new java.util.Date());
        // } catch (java.io.FileNotFoundException e) {
        //     e.printStackTrace();
        // }

        boolean IS_BACKTEST_MODE = true; 
        
        String[] csvFiles = {
            // "data/NVDA_macro_stress.csv",
            // "data/SMH_macro_stress.csv",
            // "data/NVDA_micro_stress.csv",
            // "data/SMH_micro_stress.csv"
            "data/NVDA_macro_1min.csv",
            "data/SMH_macro_1min.csv",
            "data/NVDA_micro_quotes.csv",
            "data/SMH_micro_quotes.csv"
        };
        
        String[] tickers = {"NVDA", "SMH"};
        Gson gson = new Gson();
        
        // Read execution costs from the shared config.json so the grid search can sweep them
        BacktestConfig bConfig = new BacktestConfig();
        try (java.io.FileReader cfgReader = new java.io.FileReader("../../strategy_python/config.json")) {
            bConfig = gson.fromJson(cfgReader, BacktestConfig.class);
        } catch (Exception e) {
            System.out.println("config.json not found — using default commission/slippage rates.");
        }

        Portfolio portfolio = new Portfolio(10000.0, bConfig.commission_rate, bConfig.slippage_rate);
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
            socket.setReceiveTimeOut(2000); 

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

            // 🚨 NEW: Throttle Variables
            Map<String, Long> lastSentTimestamp = new HashMap<>();
            Map<String, Double> lastSentPrice = new HashMap<>();
            long THROTTLE_MS = 50;         // Max one send per 50ms per symbol
            double PRICE_MOVE_THRESHOLD = 0.0001; // 0.01% — bypass time gate on significant moves

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
                    System.out.println("\n>>> MICRO TRADING WINDOW DETECTED. Benchmark anchored to session open prices.");
                }
                
                // Track beginning prices for the current active window
                if (!beginningPrices.containsKey(event.getSymbol())) {
                    beginningPrices.put(event.getSymbol(), event.getPrice());
                }
                
                finalPrices.put(event.getSymbol(), event.getPrice()); 
                portfolio.updateMarketPrice(event.getSymbol(), event.getPrice());

                // 🚨 THE THROTTLE LOGIC
                boolean isMacro = (event.bid_price == 0);
                long lastSend = lastSentTimestamp.getOrDefault(event.getSymbol(), 0L);
                
                if (!isMacro && (event.getTimestamp() - lastSend < THROTTLE_MS)) {
                    double lastPrice = lastSentPrice.getOrDefault(event.getSymbol(), 0.0);
                    boolean priceStationary = lastPrice <= 0 ||
                        Math.abs(event.getPrice() - lastPrice) / lastPrice <= PRICE_MOVE_THRESHOLD;
                    if (priceStationary) {
                        continue; // Within time window and no significant price move — skip
                    }
                    // Price moved beyond threshold — bypass time gate and send immediately
                }

                // Update the "last send" clock and price
                lastSentTimestamp.put(event.getSymbol(), event.getTimestamp());
                lastSentPrice.put(event.getSymbol(), event.getPrice());

                String jsonPayload = gson.toJson(event);
                String response = null;
                long latencyMicros = 0;
                int maxRetries = 5;
                for (int attempt = 0; attempt < maxRetries; attempt++) {
                    long startTime = System.nanoTime();
                    socket.send(jsonPayload);
                    response = socket.recvStr();
                    latencyMicros = (System.nanoTime() - startTime) / 1000;

                    if (response != null) break;

                    System.out.println("WARNING: Strategy timeout (attempt " + (attempt + 1) + "/" + maxRetries + "). Rebuilding socket...");
                    socket.close();
                    socket = context.createSocket(SocketType.REQ);
                    socket.connect("tcp://localhost:5555");
                    socket.setReceiveTimeOut(IS_BACKTEST_MODE ? 5000 : 1000);
                    Thread.sleep(1000);
                }

                if (response == null) {
                    System.out.println("ERROR: Strategy unreachable after " + maxRetries + " attempts. Dropping event.");
                    continue;
                }

                eventCount++;
                totalLatencyMicros += latencyMicros;
                maxLatencyMicros = Math.max(maxLatencyMicros, latencyMicros);

                // --- THE TELEMETRY PRINT ---
                // int printInterval = IS_BACKTEST_MODE ? 50000 : 10;
                // if (!isHydrating && eventCount % printInterval == 0) {
                //     System.out.println("Events Processed: " + eventCount + " | Avg Latency: " + (totalLatencyMicros / eventCount) + " µs");
                // }

                // Only process signals if we are past the hydration/macro phase
                if (!isHydrating) {
                    OrderSignal os = gson.fromJson(response, OrderSignal.class);
                    if (os.signal != null && !os.signal.equals("HOLD")) {
                        Order newOrder = portfolio.createOrder(os.signal, os.price, os.symbol, (double) os.quantity);
                        if (newOrder != null) {
                            gateway.execute(newOrder, event);
                            portfolio.applyFill(newOrder);
                        }
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}