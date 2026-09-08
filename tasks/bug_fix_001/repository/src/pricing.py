"""Pricing engine for order and item calculations."""

from typing import Any, Dict, List


def calculate_discounted_price(price: float, discount_percent: float) -> float:
    """Calculate the final price after applying a percentage discount.

    Args:
        price: Original unit or item price in dollars (must be >= 0.0).
        discount_percent: Percentage discount to apply (must be in [0.0, 100.0]).

    Returns:
        The discounted price rounded to 2 decimal places.

    Raises:
        ValueError: If price < 0.0 or discount_percent is outside [0.0, 100.0].
    """
    if price < 0.0:
        raise ValueError("Price cannot be negative.")

    # BUG 1: Missing bounds check on discount_percent (negative or > 100.0)
    # BUG 2: Subtracts discount_percent as a flat dollar amount rather than percentage!
    discounted = price - discount_percent
    return round(discounted, 2)


def calculate_cart_total(
    items: List[Dict[str, Any]],
    order_discount_percent: float = 0.0,
) -> float:
    """Calculate total price for a shopping cart of items after order discount.

    Args:
        items: List of item dictionaries with 'price' and optional 'quantity'.
        order_discount_percent: Overall discount percentage applied to order total.

    Returns:
        Total order amount rounded to 2 decimal places.
    """
    subtotal = sum(
        float(item["price"]) * int(item.get("quantity", 1)) for item in items
    )
    return calculate_discounted_price(subtotal, order_discount_percent)
