import unittest

from check_paddle import evaluate, matches, normalize, region_lines


class OCRAnchorTests(unittest.TestCase):
    def result(self):
        return {'file':'image.png','status':'success','image_width':1000,'image_height':1000,
                'lines':[{'text':'12 345,67','confidence':0.9,'polygon':[[100,100],[200,100],[200,150],[100,150]]},
                         {'text':'000289','confidence':0.95,'polygon':[[800,800],[900,800],[900,850],[800,850]]}]}

    def test_correct_text_in_wrong_part_of_page_is_not_a_match(self):
        check={'file':'image.png','bbox':[0,0,30,30],'expected':'000289'}
        report=evaluate([self.result()],[check])
        self.assertEqual(report['matched'],0)

    def test_decimal_and_leading_zero_errors_are_not_normalized_away(self):
        self.assertNotEqual(normalize('12 345,67'),normalize('1234567'))
        self.assertNotEqual(normalize('000289'),normalize('289'))
        self.assertEqual(normalize('  ЩЕБЕНЬ\n20–40 '),normalize('щебень20–40'))
        self.assertFalse(matches('126','1126'))
        self.assertFalse(matches('000289','289'))
        self.assertTrue(matches('12 345,67','Сумма: 12345,67 руб.'))
        self.assertTrue(matches('126','0345009\n126'))
        self.assertTrue(matches('000289','No\n000289\n12\n06\n07'))

    def test_missing_and_failed_pages_count_as_unmatched(self):
        check={'file':'image.png','bbox':[0,0,100,100],'expected':'000289'}
        self.assertEqual(evaluate([], [check])['matched'],0)
        failed={'file':'image.png','status':'failed'}
        self.assertEqual(evaluate([failed], [check])['matched'],0)

    def test_region_uses_page_dimensions(self):
        self.assertEqual(region_lines(self.result(),[0,0,30,30]),'12 345,67')


if __name__=='__main__':
    unittest.main()
