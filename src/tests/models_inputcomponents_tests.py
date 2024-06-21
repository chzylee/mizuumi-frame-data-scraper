import unittest
from models.inputcomponents import InputComponents

class TestInputComponents(unittest.TestCase):
    # Leaving the responsibility of value validation to other methods.
    # This class does not interact with any data sources.

    # Test ability to build from each variety of move.
    def test_from_string_given_normal_input_builds_instance(self):
        input = InputComponents.from_string("2B")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "2")
        self.assertEqual(input.button, "B")

    def test_from_string_given_charged_normal_input_builds_instance(self):
        input = InputComponents.from_string("3[C]")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "3")
        self.assertEqual(input.button, "[C]")

    def test_from_string_given_ground_special_input_builds_instance(self):
        input = InputComponents.from_string("421B")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "421")
        self.assertEqual(input.button, "B")

    def test_from_string_given_air_normal_input_builds_instance(self):
        input = InputComponents.from_string("j.A")
        self.assertEqual(input.air, "j.")
        self.assertIsNone(input.directions)
        self.assertEqual(input.button, "A")

    def test_from_string_given_air_cmd_normal_input_builds_instance(self):
        input = InputComponents.from_string("j.2B")
        self.assertEqual(input.air, "j.")
        self.assertEqual(input.directions, "2")
        self.assertEqual(input.button, "B")

    def test_from_string_given_air_special_input_builds_instance(self):
        input = InputComponents.from_string("j.214A")
        self.assertEqual(input.air, "j.")
        self.assertEqual(input.directions, "214")
        self.assertEqual(input.button, "A")

    def test_from_string_given_half_circle_special_input_builds_instance(self):
        input = InputComponents.from_string("63214C")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "63214")
        self.assertEqual(input.button, "C")

    def test_is_normal_given_ground_normal_input_returns_true(self):
        input = InputComponents(directions="3", button="C")
        self.assertTrue(input.is_normal())

    def test_is_normal_given_air_normal_input_returns_true(self):
        input = InputComponents(air="j.", button="A")
        self.assertTrue(input.is_normal())

    def test_is_normal_given_air_cmd_normal_input_returns_true(self):
        input = InputComponents(air="j.", directions="2", button="B")
        self.assertTrue(input.is_normal())

    def test_is_normal_given_charged_normal_input_returns_false(self):
        input = InputComponents(directions="5", button="[C]")
        self.assertFalse(input.is_normal())

    def test_is_normal_given_not_normal_input_returns_false(self):
        input = InputComponents(directions="236", button="A")
        self.assertFalse(input.is_normal())

    def test_is_charged_given_button_is_charged_returns_true(self):
        input = InputComponents(directions="5", button="[C]")
        self.assertTrue(input.is_charged())

    def test_is_charged_given_button_is_not_charged_returns_false(self):
        input = InputComponents(directions="5", button="C")
        self.assertFalse(input.is_charged())

    def test_is_special_given_button_is_special_returns_true(self):
        input = InputComponents(directions="421", button="B")
        self.assertTrue(input.is_special())

    def test_is_special_given_half_circle_special_returns_true(self):
        input = InputComponents.from_string("63214C")
        self.assertTrue(input.is_special())

    def test_is_special_given_button_is_not_special_returns_false(self):
        input = InputComponents(directions="2", button="B")
        self.assertFalse(input.is_special())

    def test_is_air_given_button_is_air_returns_true(self):
        input = InputComponents(air="j.", button="C")
        self.assertTrue(input.is_air())

    def test_is_air_given_button_is_not_air_returns_false(self):
        input = InputComponents(directions="5", button="C")
        self.assertFalse(input.is_air())

    def test_to_string_given_normal_returns_correct_format(self):
        input = InputComponents(directions="3", button="C")
        self.assertEqual(str(input), "3C")

    def test_to_string_given_air_normal_returns_correct_format(self):
        input = InputComponents(air="j.", button="B")
        self.assertEqual(str(input), "j.B")

    def test_to_string_given_air_cmd_normal_returns_correct_format(self):
        input = InputComponents(air="j.", directions="2", button="B")
        self.assertEqual(str(input), "j.2B")

    def test_to_string_given_special_returns_correct_format(self):
        input = InputComponents(directions="623", button="C")
        self.assertEqual(str(input), "623C")

    def test_to_string_given_air_special_returns_correct_format(self):
        input = InputComponents(air="j.", directions="236", button="C")
        self.assertEqual(str(input), "j.236C")

if __name__ == '__main__':
    unittest.main()
