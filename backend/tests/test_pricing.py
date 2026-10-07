from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace
import unittest
from app.services.pricing import hourly_slot_price, slot_charge


class SlotPricingTests(unittest.TestCase):
    def setUp(self):
        self.venue = SimpleNamespace(price_per_hour=Decimal('50'), price_rules=[])
        self.slot = SimpleNamespace(date=date(2026, 10, 14), start_time=time(18),
            end_time=time(18, 30), price_override=None)

    def test_default_rate_scales_with_duration(self):
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('25'))

    def test_special_rate_and_exclusive_end(self):
        self.venue.price_rules = [dict(type='time_range', start_time='18:00', end_time='22:00', price=80)]
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('40'))
        self.slot.start_time, self.slot.end_time = time(22), time(22, 30)
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('25'))

    def test_date_range_and_optional_time_boundary(self):
        self.venue.price_rules = [dict(type='date_range', start_date='2026-10-14',
            end_date='2026-10-14', start_time='18:00', end_time='20:00', price=120)]
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('60'))
        self.slot.date = date(2026, 10, 15)
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('25'))

    def test_explicit_override_is_used_when_no_venue_rule_matches(self):
        self.slot.price_override = Decimal('90')
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('45'))
        self.slot.price_override = Decimal('0')
        self.assertEqual(slot_charge(self.venue, self.slot), Decimal('0'))

    def test_existing_first_matching_venue_rule_precedence(self):
        self.venue.price_rules = [dict(type='daily_time', start_time='18:00', end_time='22:00', price=80),
            dict(type='time_range', start_time='18:00', end_time='22:00', price=100)]
        self.slot.price_override = Decimal('90')
        self.assertEqual(hourly_slot_price(self.venue, self.slot), Decimal('80'))

    def test_unknown_rule_does_not_override_default(self):
        self.venue.price_rules = [dict(type='unknown', price=80)]
        self.assertEqual(hourly_slot_price(self.venue, self.slot), Decimal('50'))


if __name__ == '__main__':
    unittest.main()
