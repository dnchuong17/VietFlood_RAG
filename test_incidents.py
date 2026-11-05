import unittest
import unicodedata
import re
from unittest.mock import patch
from incident_processing import (
    extract, normalize, cosine, PIPELINE, NORMALIZATION_VERSION,
    incident_embedding_fingerprint,
)


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

    def test_safe_abbreviations_without_inventing_accents(self):
        source = 'TP. Hue Q.1 P.2 ngp 0,5m; hk co nguoi macket; can cuuho'
        result = extract(source)
        self.assertEqual(result['normalizationVersion'], NORMALIZATION_VERSION)
        self.assertEqual(result['normalizedText'], source)
        self.assertIn('thanh pho hue quan 1 phuong 2 ngap 0,5m', result['matchingText'])
        self.assertFalse(result['strandedPeople'])
        self.assertTrue(result['emergency'])
        self.assertEqual(result['diacriticRestoration'], 'not_assumed')
        self.assertEqual(normalize('ngang hong; k 12; ma')['matchingText'], 'ngang hong; k 12; ma')

    def test_negation_inside_subject_and_shared_predicates(self):
        for source in [
            'Người không mắc kẹt; xe chưa chết máy',
            'Không có người mắc kẹt và đuối nước',
            'Chưa ghi nhận bất kỳ người dân nào tại khu vực này đang bị đuối nước',
            'ko ai bi nuoc cuon; hk can cuuho',
            'Không có ai không thở được',
            'Không còn ngập; không có người nguy kịch',
            'Chẳng có người bất tỉnh',
            'Có người đuối nước không?',
            'Nếu ngập sẽ có người mắc kẹt',
            'Cảnh báo nguy cơ đuối nước',
            'Không có những người đuối nước',
            'Không có người ở sông đang đuối nước',
            'khong co nhung nguoi duoi nuoc',
            'khong co nguoi o song duoi nuoc',
        ]:
            with self.subTest(source=source):
                result = extract(source)
                self.assertFalse(result['lifeThreat'])
                self.assertFalse(result['emergency'])
                self.assertFalse(result['strandedPeople'])
                self.assertFalse(result['strandedVehicles'])

    def test_explicit_life_threat_evidence_only(self):
        for source in ['Có người đuối nước', 'tre em bi nuoc cuon', 'Người nguy kịch',
                       'Có người bất tỉnh', 'Tình hình đe dọa tính mạng',
                       'Cứu với, không thở được', 'Không thể thở']:
            with self.subTest(source=source):
                result = extract(source)
                self.assertTrue(result['lifeThreat'])
                self.assertTrue(result['emergency'])
                self.assertEqual(next(f['text'] for f in result['facts'] if f['kind'] == 'life_threat'), source)
        for source in ['Ngập 3 m', 'Nước ngang ngực', '3 người mắc kẹt, cần cứu hộ',
                       'Không có ai đuối nước', 'Có thể có người nguy kịch']:
            with self.subTest(source=source):
                self.assertFalse(extract(source)['lifeThreat'])

    def test_contrast_resets_polarity_but_preserves_whole_original_clause(self):
        source = 'Không ngập nhưng có người mắc kẹt và cần cứu hộ'
        result = extract(source)
        self.assertFalse(result['hasFloodEvidence'])
        self.assertTrue(result['strandedPeople'])
        self.assertTrue(result['emergency'])
        self.assertTrue(all(f['text'] == source for f in result['facts']))
        self.assertTrue(extract('Không có người đuối nước nhưng có người nguy kịch')['lifeThreat'])
        self.assertTrue(extract('khong ngap, nhung co nguoi duoi nuoc')['lifeThreat'])

    def test_original_spans_preserve_decomposed_accents_and_spacing(self):
        source = unicodedata.normalize('NFD', '  Đường  ngập 50 cm; có người đuối nước!  ')
        result = extract(source)
        self.assertTrue(result['hasFloodEvidence'])
        self.assertTrue(result['lifeThreat'])
        for fact in result['facts']:
            self.assertIn(fact['text'], source)
        self.assertIn('  ', result['facts'][0]['text'])

    def test_depth_does_not_infer_from_unrelated_numbers_or_invalid_units(self):
        for source in ['Ngập đường dài 200 m', 'Ngập tại số 50, có 3 người',
                       'Ngập -50 cm', 'Ngập 1.2.3 m', 'Ngập 3 km',
                       'Ngập 5 m3', 'Ngập 5 m³', 'Ngập 2 cm/s', 'Ngập 2e3 m',
                       'Ngập nhưng không sâu 50 cm', 'Ngập, chưa đo độ sâu']:
            with self.subTest(source=source):
                depths = [f for f in extract(source)['facts'] if f['kind'] == 'depth']
                self.assertFalse(any(f['value'] is not None for f in depths))
        source = 'Ngập sâu 1.25 mét; ngập khoảng 25cm; ngập ngang hông'
        depths = [f for f in extract(source)['facts'] if f['kind'] == 'depth']
        self.assertEqual([(f['value'], f['unit']) for f in depths], [(1.25, 'm'), (25, 'cm'), (None, None)])

    def test_incident_fingerprint_is_versioned_and_does_not_modify_global_identity(self):
        from rag_models import embedding_fingerprint
        knowledge_identity = embedding_fingerprint()
        self.assertEqual(PIPELINE, 'incidents-v2')
        original = incident_embedding_fingerprint('base-model')
        self.assertEqual(original, incident_embedding_fingerprint('base-model'))
        self.assertNotEqual(original, 'base-model')
        self.assertNotEqual(original, incident_embedding_fingerprint('another-model'))
        with patch('incident_processing.NORMALIZATION_VERSION', 'next-version'):
            self.assertNotEqual(original, incident_embedding_fingerprint('base-model'))
        with patch('incident_processing.PIPELINE', 'incidents-next'):
            self.assertNotEqual(original, incident_embedding_fingerprint('base-model'))
        self.assertEqual(embedding_fingerprint(), knowledge_identity)

    def test_questions_and_unverified_suffixes_are_not_observations(self):
        for source in ['Có ai đuối nước?', 'Có người mắc kẹt?', 'Đường ngập 50cm?',
                       'Có người đuối nước, chưa xác minh',
                       'Có người đuối nước, chưa được xác nhận',
                       'Có người đuối nước, chỉ là tin đồn',
                       'Liệu có người đuối nước', 'Có phải người đang nguy kịch']:
            with self.subTest(source=source):
                result = extract(source)
                self.assertFalse(result['lifeThreat'])
                self.assertFalse(result['emergency'])
                self.assertFalse(result['strandedPeople'])
                self.assertFalse(result['hasFloodEvidence'])
        result = extract('Có ai đuối nước? Đường ngập 50cm; cần cứu hộ!')
        self.assertFalse(result['lifeThreat'])
        self.assertTrue(result['hasFloodEvidence'])
        self.assertTrue(result['emergency'])

    def test_normalization_preserves_numeric_and_gps_lexemes_and_original_evidence(self):
        source = 'Q.1 P.2 Đường ngp 0,50m; 03 xe chetmay; GPS +16.047079, 108.206230; mã 0012'
        result = extract(source)
        numbers = re.findall(r'[+-]?\d+(?:[.,]\d+)?', source)
        self.assertEqual(re.findall(r'[+-]?\d+(?:[.,]\d+)?', result['matchingText']), numbers)
        self.assertEqual(result['normalizedText'], source)
        self.assertTrue(result['strandedVehicles'])
        self.assertTrue(all(f['text'] in source for f in result['facts']))
        self.assertNotIn('latitude', result)
        self.assertNotIn('longitude', result)

    def test_cosine_is_finite_for_large_small_and_zero_vectors(self):
        self.assertAlmostEqual(cosine([1e308, 1e308], [1e308, 1e308]), 1.0)
        self.assertAlmostEqual(cosine([1e-300, 1e-300], [-1e-300, -1e-300]), -1.0)
        self.assertEqual(cosine([0, 0], [1, 0]), 0.0)


if __name__ == '__main__':
    unittest.main()
