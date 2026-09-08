"""Hidden verification test suite for pricing calculations.

Evaluates boundary validation, edge cases, and arithmetic correctness.
Kept outside the agent repository sandbox to prevent benchmark contamination.
"""

import pytest
from pricing import calculate_cart_total, calculate_discounted_price


def test_full_100_percent_discount():
    """A 100% discount should reduce price to 0.00."""
    assert calculate_discounted_price(89.50, 100.0) == 0.0


def test_discount_over_100_percent_raises():
    """Discounts exceeding 100% must raise ValueError."""
    with pytest.raises(ValueError, match="discount_percent"):
        calculate_discounted_price(50.0, 105.0)


def test_negative_discount_percent_raises():
    """Negative discount percentages must raise ValueError."""
    with pytest.raises(ValueError, match="discount_percent"):
        calculate_discounted_price(50.0, -10.0)


def test_fractional_discount_rounding():
    """Ensure fractional discounts are accurately rounded to two decimal places."""
    # 79.99 * (1.0 - 0.125) = 69.99125 -> 69.99
    assert calculate_discounted_price(79.99, 12.5) == 69.99


def test_zero_price_with_discount():
    """A zero base price with any valid discount remains zero."""
    assert calculate_discounted_price(0.0, 50.0) == 0.0


def test_cart_boundary_validation():
    """Cart total calculation should reject invalid discount bounds."""
    items = [{"price": 10.0, "quantity": 1}]
    with pytest.raises(ValueError):
        calculate_cart_total(items, 150.0)
