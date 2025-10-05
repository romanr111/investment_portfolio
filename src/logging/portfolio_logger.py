import logging


logger = logging.getLogger(__name__)


def log_portfolio_data(enhanced_stocks):
    """Log detailed stock positions metrics from analytics payload."""
    metadata = enhanced_stocks["metadata"]
    logger.info("=== Stock Positions Metrics ===")
    logger.info(f"Total Portfolio Value: ${metadata['total_portfolio_value']}")
    logger.info(f"Total Stocks Value: ${metadata['total_stocks_value']}")
    logger.info(f"Total Unrealized P&L: {metadata['total_unrealized_pnl_percentage']}%")
    logger.info(
        f"China Stocks Value: ${metadata['china_stocks_value']} "
        f"({metadata['china_stocks_value']/metadata['total_stocks_value']*100:.2f}%)"
    )
    logger.info(
        f"Regular Stocks Value: ${metadata['regular_stocks_value']} "
        f"({metadata['regular_stocks_value']/metadata['total_stocks_value']*100:.2f}%)"
    )

    # Log China Stocks details
    logger.info("\nChina Stocks:")
    for symbol, details in enhanced_stocks["China Stocks"].items():
        logger.info(f"  {symbol}:")
        logger.info(f"    Market Value: ${details['market_value']}")
        logger.info(f"    Quantity: {details['quantity']} shares")
        logger.info(f"    Avg Price: ${details['avg_price']:.2f}")
        logger.info(f"    Current Price: ${details['current_price']:.2f}")
        logger.info(f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%")
        logger.info(
            f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%"
        )
        logger.info(f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%")

    # Log Regular Stocks details
    logger.info("\nRegular Stocks:")
    for symbol, details in enhanced_stocks["Stocks"].items():
        logger.info(f"  {symbol}:")
        logger.info(f"    Market Value: ${details['market_value']}")
        logger.info(f"    Quantity: {details['quantity']} shares")
        logger.info(f"    Avg Price: ${details['avg_price']:.2f}")
        logger.info(f"    Current Price: ${details['current_price']:.2f}")
        logger.info(f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%")
        logger.info(
            f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%"
        )
        logger.info(f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%")


def log_portfolio_metadata(metadata):
    """Log portfolio-level metrics when only metadata is available."""
    logger.info("=== Stock Positions Metrics (Pre-Existing) ===")
    logger.info(
        f"Total Portfolio Value: ${metadata.get('total_portfolio_value', 'N/A')}"
    )
    logger.info(f"Total Stocks Value: ${metadata.get('total_stocks_value', 'N/A')}")
    logger.info(
        f"Total Unrealized P&L: {metadata.get('total_unrealized_pnl_percentage', 'N/A')}%"
    )

    total_stocks_value = metadata.get("total_stocks_value", 0)
    china_stocks_value = metadata.get("china_stocks_value", 0)
    regular_stocks_value = metadata.get("regular_stocks_value", 0)

    if total_stocks_value > 0:
        logger.info(
            f"China Stocks Value: ${china_stocks_value} "
            f"({china_stocks_value/total_stocks_value*100:.2f}%)"
        )
        logger.info(
            f"Regular Stocks Value: ${regular_stocks_value} "
            f"({regular_stocks_value/total_stocks_value*100:.2f}%)"
        )
