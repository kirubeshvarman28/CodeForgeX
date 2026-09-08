"""Public test suite for pricing calculations."""

import pytest
from pricing import calculate_cart_total, calculate_discounted_price


def test_zero_discount():
    """Applying a 0% discount should leave price unchanged."""
    assert calculate_discounted_price(100.0, 0.0) == 100.0


def test_negative_price_raises_value_error():
    """Negative prices must raise ValueError."""
    with pytest.raises(ValueError, match="Price cannot be negative"):
        calculate_discounted_price(-10.0, 10.0)


def test_percentage_discount_calculation():
    """A $50.00 item with a 20% discount should cost $40.00."""
    # 50.0 * (1.0 - 0.20) = 40.0
    assert calculate_discounted_price(50.0, 20.0) == 40.0


def test_cart_with_discount():
    """Shopping cart with multiple items and order-level discount."""
    cart = [
        {"price": 15.0, "quantity": 2},  # 30.0
        {"price": 20.0, "quantity": 1},  # 20.0
    ]
    # Subtotal is $50.00. 10% discount yields $45.00
    assert calculate_cart_total(cart, 10.0) == 45.0
