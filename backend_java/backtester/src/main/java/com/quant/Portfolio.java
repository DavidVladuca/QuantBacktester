package com.quant;

import java.util.HashMap; 
import java.util.Map; 

public class Portfolio {
    private double cash;
    private Map<String, Double> positions;
    private double initialInvestment;

    // risk management 
    private final double DRY_POWDER_RATIO = 0.25; 
    private Map<String, Double> lastKnownPrices; 

    // Market Friction Models — injected from config.json so grid search can sweep them
    private final double commissionRate;
    private final double slippageRate;
    private double totalFeesPaid = 0.0;

    public Portfolio(double startingCash, double commissionRate, double slippageRate) {
        this.cash = startingCash;
        this.initialInvestment = startingCash;
        this.commissionRate = commissionRate;
        this.slippageRate = slippageRate;
        this.positions = new HashMap<String, Double>();
        this.lastKnownPrices = new HashMap<>();
    }

    public void updateMarketPrice(String symbol, double currentPrice) {
        this.lastKnownPrices.put(symbol, currentPrice);
    }

    private double getTotalEquity() {
        double equity = this.cash;
        for (Map.Entry<String, Double> position : positions.entrySet()) {
            String sym = position.getKey();
            double shares = position.getValue();
            double currentPrice = lastKnownPrices.getOrDefault(sym, 0.0);
            equity += (shares * currentPrice);
        }
        return equity;
    }

    // 🚨 NEW: Calculates absolute exposure (Margin Used) for both Longs and Shorts
    private double getCurrentlyDeployed() {
        double deployed = 0.0;
        for (Map.Entry<String, Double> position : positions.entrySet()) {
            String sym = position.getKey();
            double shares = Math.abs(position.getValue()); // Absolute value is the secret!
            double currentPrice = lastKnownPrices.getOrDefault(sym, 0.0);
            deployed += (shares * currentPrice);
        }
        return deployed;
    }

    public Order createOrder(String signal, double price, String symbol, double quantity) { 
        updateMarketPrice(symbol, price); 
        double currentShares = positions.getOrDefault(symbol, 0.0);
        double targetShares = quantity;
        
        if (targetShares <= 0) return null; // Safety check

        // --- INITIATE NEW POSITIONS (LONG OR SHORT) ---
        if (signal.equals("BUY") || signal.equals("SELL")) { 
            
            // Java Safety Net: Ensure we actually have the buying power Python thinks we have
            double maxAllowedDeployed = getTotalEquity() * (1.0 - DRY_POWDER_RATIO); 
            double currentlyDeployed = getCurrentlyDeployed();
            double availableToDeploy = Math.max(0, maxAllowedDeployed - currentlyDeployed);
            
            double capitalRequired = targetShares * price;

            // If Python's calculated shares exceed Java's actual available cash, clamp it down
            if (capitalRequired > availableToDeploy) {
                targetShares = availableToDeploy / price;
            }

            if (targetShares > 0) { 
                String orderId = java.util.UUID.randomUUID().toString(); 
                Order.Side side = signal.equals("BUY") ? Order.Side.BUY : Order.Side.SELL;
                return new Order(orderId, symbol, side, Order.Type.MARKET, targetShares, price); 
            }
        } 
        
        // --- CLOSING POSITIONS ---
        else if (signal.equals("SELL_TO_CLOSE") && currentShares > 0) { 
            // Safety: Ensure we don't sell more than we own
            double sharesToSell = Math.min(targetShares, currentShares);
            if (sharesToSell > 0) {
                String orderId = java.util.UUID.randomUUID().toString();
                return new Order(orderId, symbol, Order.Side.SELL, Order.Type.MARKET, sharesToSell, price);
            }
        }
        else if (signal.equals("BUY_TO_COVER") && currentShares < 0) { 
            // Safety: Ensure we don't cover more than we are short
            double sharesToBuy = Math.min(targetShares, Math.abs(currentShares));
            if (sharesToBuy > 0) {
                String orderId = java.util.UUID.randomUUID().toString();
                return new Order(orderId, symbol, Order.Side.BUY, Order.Type.MARKET, sharesToBuy, price);
            }
        }
        return null;
    }

    public void applyFill(Order order) { 
        if (order.getStatus() == Order.Status.FILLED) { 
            String symbol = order.getSymbol(); 
            double currentShares = positions.getOrDefault(symbol, 0.0);
            double fillPrice = order.getExecutionPrice();
            double fees = order.getFeesPaid();

            // Simulate Friction
            if (fillPrice == 0.0) {
                fillPrice = (order.getSide() == Order.Side.BUY) ?
                            order.getLimitPrice() * (1 + slippageRate) :
                            order.getLimitPrice() * (1 - slippageRate);
                fees = (order.getFilledQuantity() * fillPrice) * commissionRate;
                order.setExecutionData(fillPrice, fees);
            }

            this.totalFeesPaid += fees;

            if (order.getSide() == Order.Side.BUY) { 
                double totalCost = (order.getFilledQuantity() * fillPrice) + fees; 
                double newShares = currentShares + order.getFilledQuantity();

                this.cash -= totalCost;
                if (newShares == 0.0) positions.remove(symbol);
                else positions.put(symbol, newShares);
                
            } else if (order.getSide() == Order.Side.SELL) { 
                double revenue = (order.getFilledQuantity() * fillPrice) - fees; 
                double newShares = currentShares - order.getFilledQuantity();

                this.cash += revenue;
                if (newShares == 0.0) positions.remove(symbol);
                else positions.put(symbol, newShares);
            } 
            
            System.out.printf("[EXECUTED] %s %.2f %s @ $%.2f | Fee: $%.2f%n",
                              order.getSide(), order.getFilledQuantity(), symbol, fillPrice, fees);
        } 
    }

    public void printSummary(Map<String, Double> beginningPrices, Map<String, Double> finalPrices) { 
        double totalPortfolioValue = cash; 
        
        System.out.println("\n--- FINAL INVENTORY ---");
        for (Map.Entry<String, Double> position : positions.entrySet()) {
            String sym = position.getKey();
            double shares = position.getValue();
            double finalPrice = finalPrices.getOrDefault(sym, 0.0); 
            totalPortfolioValue += (shares * finalPrice); 
            System.out.println(sym + ": " + shares + " shares");
        } 
       
        double profitLoss = totalPortfolioValue - initialInvestment;
        double returnPercent = (profitLoss / initialInvestment) * 100;
        
        double benchmarkFinalValue = 0.0;
        double startingCashPerAsset = initialInvestment / beginningPrices.size();

        for (Map.Entry<String, Double> entry : beginningPrices.entrySet()) {
            String sym = entry.getKey();
            double startPrice = entry.getValue();
            double endPrice = finalPrices.getOrDefault(sym, 0.0);
            double benchmarkShares = startingCashPerAsset / startPrice;
            benchmarkFinalValue += (benchmarkShares * endPrice);
        }

        double benchmarkReturn = ((benchmarkFinalValue - initialInvestment) / initialInvestment) * 100;
        double alpha = returnPercent - benchmarkReturn; 

        System.out.println("\n--- FINAL PERFORMANCE REPORT ---");
        System.out.println("Final Cash: $" + String.format("%.2f", cash));
        System.out.println("Total Account Value: $" + String.format("%.2f", totalPortfolioValue));
        System.out.println("Total Profit/Loss: $" + String.format("%.2f", profitLoss));
        System.out.println("Total Fees Paid: $" + String.format("%.2f", totalFeesPaid));

        System.out.println("\n--- STRATEGY VS EQUAL-WEIGHT BENCHMARK ---");
        System.out.println("Bot Total Return: " + String.format("%.2f", returnPercent) + "%");
        System.out.println("Buy & Hold Return: " + String.format("%.2f", benchmarkReturn) + "%");
        
        if (alpha > 0) {
            System.out.println("Strategy Alpha: +" + String.format("%.2f", alpha) + "% (BEATING THE MARKET)");
        } else {
            System.out.println("Strategy Alpha: " + String.format("%.2f", alpha) + "% (UNDERPERFORMING)");
        }
        System.out.println("--------------------------------\n");
    }
}