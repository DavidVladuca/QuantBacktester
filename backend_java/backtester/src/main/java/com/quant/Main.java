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

        // we dont use these now, but we try to capture them just in case
        private double bid_price;
        private double ask_price;
        private double bid_size;
        private double ask_size;

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
        public double getBidPrice() { return bid_price; }
        public double getAskPrice() { return ask_price; }
        public double getBidSize() { return bid_size; }
        public double getAskSize() { return ask_size; }
    }

    public static void main(String[] args) {
        // output on a log file
        try {
            java.io.PrintStream logFile = new java.io.PrintStream(new java.io.FileOutputStream("engine_log.txt"));
            System.setOut(logFile);
            System.setErr(logFile);
            System.out.println(">>> LOGGING INITIATED: " + new java.util.Date());
        } catch (java.io.FileNotFoundException e) {
            e.printStackTrace();
        }

        boolean IS_BACKTEST_MODE = true; // set to false for live trading
        int LIVE_BAR_TIMEFRAME_MINUTES = 5;
        
        // here add your files for backtesting
        String[] csvFiles = {
            "data/NVDA_macro_5min.csv",
            "data/SMH_macro_5min.csv"
            // "data/NVDA_micro_quotes_5min.csv",
            // "data/SMH_micro_quotes_5min.csv"
        };
        
        String[] tickers = {"NVDA", "SMH"};
        Gson gson = new Gson();
        
        // read from config.json
        BacktestConfig bConfig = new BacktestConfig();
        try (java.io.FileReader cfgReader = new java.io.FileReader("../../strategy_python/config.json")) {
            bConfig = gson.fromJson(cfgReader, BacktestConfig.class);
        } catch (Exception e) {
            System.out.println("config.json not found — using default commission/slippage rates.");
        }

        Portfolio portfolio = new Portfolio(10000.0, bConfig.commission_rate, bConfig.slippage_rate);
        ExecutionGateway gateway = IS_BACKTEST_MODE
            ? new SimulatedGateway(bConfig.commission_rate, bConfig.slippage_rate)
            : new AlpacaGateway();

        Map<String, Double> finalPrices = new HashMap<>(); 
        Map<String, Double> beginningPrices = new HashMap<>();
        BlockingQueue<MarketEvent> eventQueue = new LinkedBlockingQueue<>();
        
        // to see if we switched to micro ticks in backtest
        boolean transitionedToMicro = false;

        System.out.println("Booting Engine: Connecting to Strategy...");

        try (ZContext context = new ZContext()) {
            ZMQ.Socket socket = context.createSocket(SocketType.REQ);
            socket.connect("tcp://localhost:5555");
            socket.setReceiveTimeOut(2000); 

            // initialising hidration
            // true even in backtest to hidrate macro data before switching to micro ticks
            boolean isHydrating = true;  
            
            if (IS_BACKTEST_MODE) {
                System.out.println("Initiating Pure CSV Backtest Run...");
                CSVStreamer csvStreamer = new CSVStreamer(eventQueue, csvFiles);
                new Thread(() -> csvStreamer.start()).start();
            } else {
                System.out.println("Initiating Alpaca PAPER live mode with REST hydration...");

                int barsPerStock = 100;
                AlpacaRESTFetcher hydrator = new AlpacaRESTFetcher(
                    eventQueue,
                    tickers,
                    barsPerStock,
                    LIVE_BAR_TIMEFRAME_MINUTES
                );

                new Thread(() -> hydrator.start()).start();

                isHydrating = true;
            }

            long totalLatencyMicros = 0;
            long maxLatencyMicros = 0;
            long eventCount = 0;
            long startTimer = System.currentTimeMillis();

            // throtle variables (to not overwhelm strategy with too many events)
            Map<String, Long> lastSentTimestamp = new HashMap<>();
            Map<String, Double> lastSentPrice = new HashMap<>();

            while (true) { 
                MarketEvent event = eventQueue.take(); 
                eventCount++;
                
                if ("HYDRATION_COMPLETE".equals(event.getType())) {
                    System.out.println("\n>>> HYDRATION COMPLETE. Starting live Alpaca stream...");

                    isHydrating = false;

                    LiveMarketStreamer streamer = new LiveMarketStreamer(eventQueue, tickers, LIVE_BAR_TIMEFRAME_MINUTES);
                    new Thread(() -> streamer.start()).start();

                    continue;
                }

                // if (!IS_BACKTEST_MODE) {
                //     System.out.println(
                //         "[TICK RECEIVED] #" + eventCount +
                //         " | symbol=" + event.getSymbol() +
                //         " | price=" + event.getPrice() +
                //         " | ts=" + event.getTimestamp()
                //     );
                // }

                if ("END_OF_STREAM".equals(event.getType())) {
                    System.out.println("\n=== ENGINE SHUTDOWN ===");
                    portfolio.printSummary(beginningPrices, finalPrices);
                    break; 
                }

                // transition logic
                if (IS_BACKTEST_MODE && !transitionedToMicro) {
                    transitionedToMicro = true;
                    isHydrating = false;
                    System.out.println("\n>>> BACKTEST TRADING MODE ACTIVE.");
                }
                                
                // track beginning prices for the current active window
                if (!beginningPrices.containsKey(event.getSymbol())) {
                    beginningPrices.put(event.getSymbol(), event.getPrice());
                }
                
                finalPrices.put(event.getSymbol(), event.getPrice()); 
                portfolio.updateMarketPrice(event.getSymbol(), event.getPrice());

                // update the "last send" clock and price
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

                
                totalLatencyMicros += latencyMicros;
                maxLatencyMicros = Math.max(maxLatencyMicros, latencyMicros);

                long heartbeatInterval = IS_BACKTEST_MODE ? 500_000 : 50;

                if (eventCount % heartbeatInterval == 0) {
                    long elapsedMs = System.currentTimeMillis() - startTimer;
                    double speed = eventCount / (elapsedMs / 1000.0);

                    System.out.println(
                        "[HEARTBEAT] Events=" + eventCount +
                        " | Speed=" + String.format("%.0f", speed) + " ev/s" +
                        " | Avg Latency=" + (totalLatencyMicros / eventCount) + " µs"
                    );
                }

                // only process signals if we are past the hydration/macro phase
                if (!isHydrating) {
                    OrderSignal os = gson.fromJson(response, OrderSignal.class);
                    if (os == null || os.signal == null) {
                        continue;
                    }
                    System.out.println(
                        "[STRATEGY] signal=" + os.signal +
                        " | symbol=" + os.symbol +
                        " | price=" + os.price +
                        " | qty=" + os.quantity
                    );
                    if (os.signal != null && !os.signal.equals("HOLD")) {
                        Order newOrder = portfolio.createOrder(os.signal, os.price, os.symbol, (double) os.quantity);
                        if (newOrder == null) {
                            System.out.println("[PORTFOLIO] Order REJECTED (null)");
                        } else {
                            System.out.println(
                                "[PORTFOLIO] Order CREATED | " +
                                newOrder.getSide() + " " +
                                newOrder.getQuantity() + " " +
                                newOrder.getSymbol() +
                                " @ " + newOrder.getLimitPrice()
                            );
                        }
                        if (newOrder != null) {
                            System.out.println(
                                "[EXECUTION] Sending to gateway | " +
                                newOrder.getSide() + " " +
                                newOrder.getQuantity() + " " +
                                newOrder.getSymbol()
                            );
                            gateway.execute(newOrder, event);
                            System.out.println(
                                "[FILL] Executed | " +
                                newOrder.getSide() + " " +
                                newOrder.getQuantity() + " " +
                                newOrder.getSymbol() +
                                " @ " + newOrder.getExecutionPrice() +
                                " | fees=" + newOrder.getFeesPaid()
                            );
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