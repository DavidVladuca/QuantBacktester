package com.quant; 

public class SimulatedGateway implements ExecutionGateway { 

    private final double commissionRate;
    private final double slippageRate;

    public SimulatedGateway(double commissionRate, double slippageRate) {
        this.commissionRate = commissionRate;
        this.slippageRate = slippageRate;
    }

    @Override
    public void execute(Order order, Main.MarketEvent currentMarket) {

        if (order.getStatus() == Order.Status.NEW) {

            double marketPrice = currentMarket.getPrice();
            double executedPrice;

            // apply slippage
            if (order.getSide() == Order.Side.BUY) {
                executedPrice = marketPrice * (1.0 + slippageRate);
            } else {
                executedPrice = marketPrice * (1.0 - slippageRate);
            }

            // compute fees
            double notional = executedPrice * order.getQuantity();
            double fee = notional * commissionRate;

            order.setExecutionData(executedPrice, fee);
            order.addFill(order.getQuantity());

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