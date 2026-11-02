"""Evidence-preserving Vietnamese incident analysis; independent of the knowledge index."""
import math
import re
import unicodedata

PIPELINE = 'incidents-v1'


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c)).replace('đ', 'd').replace('Đ', 'D').lower()


def normalize(text):
    text = unicodedata.normalize('NFC', text)
    folded = fold(text)
    replacements = {'ko': 'khong', 'khg': 'khong', 'hok': 'khong', 'dc': 'duoc', 'đc': 'duoc', 'ngp': 'ngap', 'ngappp': 'ngap', 'ngâp': 'ngap', 'cuuho': 'cuu ho'}
    for word, replacement in replacements.items():
        folded = re.sub(r'\b' + re.escape(word) + r'\b', replacement, folded)
    folded = re.sub(r'\bk\s+(?=(?:di|qua|co|the|duoc)\b)', 'khong ', folded)
    folded = re.sub(r'\bq\.\s*', 'quan ', folded)
    folded = re.sub(r'\bp\.\s*', 'phuong ', folded)
    return {'normalizedText': re.sub(r'\s+', ' ', text).strip(), 'matchingText': re.sub(r'\s+', ' ', folded).strip(), 'diacriticRestoration': 'not_assumed'}


def embedding_text(result):
    # Keep Vietnamese diacritics while supplying an expanded spelling variant.
    return "\n".join(dict.fromkeys([result['normalizedText'], result['matchingText']]))


def positive(text, pattern):
    for match in re.finditer(pattern, text):
        prefix = re.split(r'\b(?:nhung|tuy nhien|con|va)\b', text[:match.start()])[-1][-40:]
        if not re.search(r'\b(?:khong|chua|ko)(?:\s+(?:co|con|bi|ai|nguoi|xe))*\s*$', prefix):
            return True
    return False


def extract(description):
    normalized = normalize(description)
    facts = []
    blocked = people = vehicles = emergency = flood = False
    clauses = [s.strip() for s in re.split(r'[;!?\n]|\.(?!\d)', unicodedata.normalize('NFC', description)) if s.strip()]
    for clause in clauses:
        text = normalize(clause)['matchingText']
        is_flood = positive(text, r'\b(?:ngap|lut|lu quet|nuoc dang|nuoc len)\b')
        is_blocked = positive(text, r'\b(?:duong (?:bi )?(?:chan|tac|chia cat)|khong the (?:di|qua)|khong di (?:qua|duoc)|khong qua duoc|cam duong)\b')
        is_people = positive(text, r'\b(?:(?:nguoi|tre em|nguoi gia|gia dinh).{0,25}(?:mac ket|ket lai)|(?:mac ket|ket lai).{0,25}(?:nguoi|tre em|nguoi gia))\b')
        is_vehicles = positive(text, r'\b(?:(?:xe|o to|xe may).{0,25}(?:mac ket|ket lai|chet may)|(?:mac ket|ket lai).{0,25}(?:xe|o to|xe may))\b')
        is_emergency = positive(text, r'\b(?:cuu voi|can cuu ho|can cuu tro|mac ket|duoi nuoc|nguy kich)\b')
        for kind, present in [('condition', is_flood), ('blocked_road', is_blocked), ('stranded_people', is_people), ('stranded_vehicles', is_vehicles), ('emergency', is_emergency)]:
            if present:
                facts.append({'kind': kind, 'text': clause})
        if is_flood:
            for match in re.finditer(r'\b(\d+(?:[.,]\d+)?)\s*(cm|m|met)\b', text):
                value = float(match[1].replace(',', '.'))
                facts.append({'kind': 'depth', 'text': clause, 'value': value, 'unit': 'cm' if match[2] == 'cm' else 'm'})
            if re.search(r'\b(?:dau goi|ngang hong|ngang bung|ngang nguc)\b', text):
                facts.append({'kind': 'depth', 'text': clause, 'value': None, 'unit': None})
        flood |= is_flood
        blocked |= is_blocked
        people |= is_people
        vehicles |= is_vehicles
        emergency |= is_emergency
    return {**normalized, 'facts': facts[:100], 'blockedRoad': blocked, 'strandedPeople': people,
            'strandedVehicles': vehicles, 'emergency': emergency, 'hasFloodEvidence': flood,
            'ambiguousLocation': bool(re.search(r'\b(?:khong ro|khong biet) (?:vi tri|dia chi)\b', normalized['matchingText']))}


def cosine(a, b):
    if not a or len(a) != len(b) or not all(math.isfinite(v) for v in a + b):
        raise ValueError('Invalid vectors')
    norm = math.sqrt(sum(v*v for v in a) * sum(v*v for v in b))
    return sum(x*y for x, y in zip(a, b)) / norm if norm else 0.0
