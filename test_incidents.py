import unittest
from incident_processing import extract, normalize, cosine


class IncidentAnalysisTests(unittest.TestCase):
    def test_vietnamese_variants(self):
        for text in ['Đường ngập 50 cm, xe chết máy', 'duong ngap 50cm xe chet may', 'duong ngp 50 cm xe chet may']:
            result = extract(text)
            self.assertTrue(result['hasFloodEvidence'])
            self.assertTrue(result['strandedVehicles'])
            self.assertEqual(next(f for f in result['facts'] if f['kind'] == 'depth')['value'], 50)
            for fact in result['facts']:
                self.assertIn(fact['text'], text)

    def test_negation(self):
        result = extract('Đường không ngập. Không có người mắc kẹt. Không có xe chết máy.')
        self.assertFalse(result['hasFloodEvidence'])
        self.assertFalse(result['strandedPeople'])
        self.assertFalse(result['strandedVehicles'])
        self.assertFalse(result['emergency'])

    def test_access_negation_means_blockage(self):
        self.assertTrue(extract('ngap sau, k di dc')['blockedRoad'])
        self.assertTrue(extract('Nước ngập. Không thể qua đường')['blockedRoad'])

    def test_unknown_depth_is_not_converted(self):
        facts = extract('Ngập tới đầu gối')['facts']
        self.assertIsNone(next(f for f in facts if f['kind'] == 'depth')['value'])

    def test_explicit_units_and_conflicts(self):
        depths = [f for f in extract('Ngập 0,5 m; ngập 80 cm')['facts'] if f['kind'] == 'depth']
        self.assertEqual([(f['value'], f['unit']) for f in depths], [(0.5, 'm'), (80, 'cm')])

    def test_stranded_people_are_mentions_not_population(self):
        result = extract('Ngập đường; 3 người mắc kẹt, cần cứu hộ')
        self.assertTrue(result['strandedPeople'])
        self.assertTrue(result['emergency'])
        self.assertNotIn('population', result)

    def test_normalization_preserves_number_and_negation(self):
        text = normalize('ko ngập 20cm')
        self.assertEqual(text['normalizedText'], 'ko ngập 20cm')
        self.assertIn('khong ngap 20cm', text['matchingText'])

    def test_invalid_vectors(self):
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1)
        with self.assertRaises(ValueError):
            cosine([float('nan')], [1])
        with self.assertRaises(ValueError):
            cosine([1], [1, 2])


if __name__ == '__main__':
    unittest.main()
