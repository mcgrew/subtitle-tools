
import unittest
import ocr


class SpellCheckerTest(unittest.TestCase):
    def setUp(self):
        self.spellchecker = ocr.SpellChecker()

    def test_check1(self):
        strings = ['F—f-f-f-f. . .', 'F-f-f-F-f...', 'F--f-f-f...',
                   'F-f-f-f-f...', 'F-f-f-f-f. . .', 'F-f-f-f-f...',
                   'F-f-f-f-f. . .']
        result = self.spellchecker.check(strings)
        self.assertEqual(result, 'F-f-f-f-f...')

    def test_check2(self):
        strings = ["Wow, that con versation's on another level!",
                   "Wow, that conversation''s on another level!",
                   "Wow, that conversation’'s on another level!",
                   "Wow, that conversation’'s on another level!",
                   "Wow, that conversation's on another level!",
                   'Wow, that con versation’s on another level!',
                   'Wow, that conversation’s on another level!',
                   'Wow, that con versatianis on another level!']
        result = self.spellchecker.check(strings)
        self.assertEqual(result, "Wow, that conversation's on another level!")

    def test_check3(self):
        strings = ["This bl0ckhead was absurd enough to say",
                   "This bloc/(head was absurd enough to say",
                   "Th!s blockhead was absurd enough to say",
                   "This blockhead was absurd en0ugh to say",
                   "Th|s blockhead was absurd en0ugh to say",
                   "This bl0ckhead was absurd enough to say",
                   "Th|s blockhead was absurd enough to say"]
        result = self.spellchecker.check(strings)
        self.assertEqual(result, "This blockhead was absurd enough to say")

    def tearDown(self):
        pass
