package com.quant; 

public class SimulatedGateway implements ExecutionGateway { 

    @Override
    public void execute(Order order, Main.MarketEvent currentMarket) {

        if (order.getStatus() == Order.Status.NEW) {

            double marketPrice = currentMarket.getPrice();

            // apply slippage
            double slippageRate = 0.0005; 
            double executedPrice;

            if (order.getSide() == Order.Side.BUY) {
                executedPrice = marketPrice * (1.0 + slippageRate);
            } else {
                executedPrice = marketPrice * (1.0 - slippageRate);
            }

            // compute fees
            double commissionRate = 0.0001;
            double notional = executedPrice * order.getQuantity();
            double fee = notional * commissionRate;

            order.setExecutionData(executedPrice, fee);
            order.addFill(order.getQuantity());

            // just logs
            System.out.println(
                "[GATEWAY] Executed " +
                order.getSide() + " " +
                order.getQuantity() + " " +
                order.getSymbol() +
                " @ $" + String.format("%.2f", executedPrice) +
                " | Fee: $" + String.format("%.2f", fee)
            );
        }
    }
} 