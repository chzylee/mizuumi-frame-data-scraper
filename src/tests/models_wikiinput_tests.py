import unittest
from models.wikiinput import WikiInputComponents

class TestWikiInputComponents(unittest.TestCase):
    # Ensure this still preserves behavior of normal InputComponents
    def test_from_string_given_normal_input_builds_instance(self):
        input = WikiInputComponents.from_string("2B")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "2")
        self.assertEqual(input.button, "B")

    def test_from_string_given_charged_normal_input_builds_instance(self):
        input = WikiInputComponents.from_string("3[C]")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "3")
        self.assertEqual(input.button, "[C]")

    def test_from_string_given_ground_special_input_builds_instance(self):
        input = WikiInputComponents.from_string("421B")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "421")
        self.assertEqual(input.button, "B")

    def test_from_string_given_air_normal_input_builds_instance(self):
        input = WikiInputComponents.from_string("j.A")
        self.assertEqual(input.air, "j.")
        self.assertIsNone(input.directions)
        self.assertEqual(input.button, "A")

    def test_from_string_given_air_cmd_normal_input_builds_instance(self):
        input = WikiInputComponents.from_string("j.2B")
        self.assertEqual(input.air, "j.")
        self.assertEqual(input.directions, "2")
        self.assertEqual(input.button, "B")

    def test_from_string_given_air_special_input_builds_instance(self):
        input = WikiInputComponents.from_string("j.214A")
        self.assertEqual(input.air, "j.")
        self.assertEqual(input.directions, "214")
        self.assertEqual(input.button, "A")

    def test_from_string_given_half_circle_special_input_builds_instance(self):
        input = WikiInputComponents.from_string("63214C")
        self.assertIsNone(input.air)
        self.assertEqual(input.directions, "63214")
        self.assertEqual(input.button, "C")

    def test_from_string_given_multiple_buttons_in_input_builds_instance(self):
        # Wiki label for C-Aoko air orb. Common case for special with multiple versions.
        input = WikiInputComponents.from_string("j.214A/[A]/B/[B]/C")
        self.assertIsNotNone(input.air)
        self.assertEqual(input.directions, "214")
        self.assertEqual(input.button, "A/[A]/B/[B]/C")

    def test_from_string_given_generic_button_in_input_builds_instance(self):
        # Wiki label for C-Aoko air orb. Common case for special with multiple versions.
        input = WikiInputComponents.from_string("j.22X")
        self.assertIsNotNone(input.air)
        self.assertEqual(input.directions, "22")
        self.assertEqual(input.button, "X")

if __name__ == '__main__':
    unittest.main()
