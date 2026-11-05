"""Evidence-preserving Vietnamese incident analysis; independent of the knowledge index."""
import hashlib
import json
import math
import re
import unicodedata

PIPELINE = 'incidents-v2'
NORMALIZATION_VERSION = 'vi-incidents-2'


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c)).replace('đ', 'd').replace('Đ', 'D').lower()


def normalize(text):
    # Never guess missing accents. Only the matching variant expands known tokens;
    # normalizedText remains a readable, whitespace/NFC-normalized source variant.
    source = unicodedata.normalize('NFC', text)
    matching = fold(source)
    replacements = {
        'ko': 'khong', 'khg': 'khong', 'khongg': 'khong', 'khum': 'khong',
        'hok': 'khong', 'hk': 'khong', 'k0': 'khong',
        'dc': 'duoc', 'ngp': 'ngap', 'ngapp': 'ngap',
        'ngappp': 'ngap', 'cuuho': 'cuu ho', 'cuutro': 'cuu tro',
        'macket': 'mac ket', 'chetmay': 'chet may', 'khongthe': 'khong the',
    }
    # Do not expand ambiguous single letters globally (k may denote a location).
    for word, replacement in replacements.items():
        matching = re.sub(r'\b' + re.escape(word) + r'\b', replacement, matching)
    matching = re.sub(r'\bk\s+(?=(?:di|qua|co|con|ai|the|duoc|ngap|bi|can|mac|duoi|nguy)\b)', 'khong ', matching)
    matching = re.sub(r'\bq\.\s*', 'quan ', matching)
    matching = re.sub(r'\bp\.\s*', 'phuong ', matching)
    matching = re.sub(r'\btp\.\s*', 'thanh pho ', matching)
    return {
        'normalizationVersion': NORMALIZATION_VERSION,
        'normalizedText': re.sub(r'\s+', ' ', source).strip(),
        'matchingText': re.sub(r'\s+', ' ', matching).strip(),
        'diacriticRestoration': 'not_assumed',
    }


def incident_embedding_fingerprint(base_fingerprint):
    """Version incident embeddings without touching the knowledge-index identity."""
    identity = {'embedding_fingerprint': base_fingerprint,
                'normalization_version': NORMALIZATION_VERSION, 'pipeline': PIPELINE}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def embedding_text(result):
    # Keep Vietnamese diacritics while supplying an expanded spelling variant.
    return "\n".join(dict.fromkeys([result['normalizedText'], result['matchingText']]))


_NEGATION = re.compile(r'\b(?:khong|chua|chang|cha|dau co)\b')
_UNCERTAIN = re.compile(r'\b(?:neu|gia su|nguy co|co the|canh bao|de phong|nghe noi|lieu|co phai|chua (?:duoc )?xac (?:minh|nhan))\b')
# Split contrast BEFORE accent folding: 'những' is not 'nhưng', and 'sông'
# is not the conjunction 'song'. Accentless 'nhung' is only safe after a comma.
_CONTRAST = re.compile(r'\b(?:nhưng|tuy nhiên|tuy nhien)\b|,\s*nhung\b', re.I)


def positive(text, pattern, *, inability=False):
    """Conservative polarity: shared negation survives 'va' and long subjects.

    An explicit contrast starts a new scope. Negation inside a subject/predicate
    also counts. Inability expressions are positive only for blocked access or
    breathing failure, not by removing 'khong' from arbitrary text.
    """
    for scope in text.split('\x1e'):
        for match in re.finditer(pattern, scope):
            prefix = scope[:match.start()]
            evidence = match.group()
            if _NEGATION.search(prefix) or _UNCERTAIN.search(prefix + evidence):
                continue
            if _NEGATION.search(evidence) and not inability:
                continue
            # Questions and explicit denials after the predicate are not evidence.
            suffix = scope[match.end():]
            if re.match(r'\s*(?:khong|chua|la sai|khong dung|khong co that)\b', suffix):
                continue
            if re.match(r'\s*,?\s*(?:la sai|khong dung|khong co that|chua (?:duoc )?xac (?:minh|nhan)|(?:chi la )?tin don)\b', suffix):
                continue
            return True
    return False


def _clauses(description):
    # Slice ORIGINAL code points (including decomposed accents), not NFC copies.
    # Decimal separators and short address abbreviations are not sentence ends.
    start = 0
    for match in re.finditer(r'[;!?\n]|\.(?!\d)', description):
        if match.group() == '.' and re.search(r'\b(?:q|p|tp)$', description[start:match.start()], re.I):
            continue
        clause = description[start:match.start()].strip()
        # A question is not an asserted observation. Keep its punctuation out of
        # evidence without turning the interrogative into a positive fact.
        if clause and match.group() != '?':
            yield clause
        start = match.end()
    clause = description[start:].strip()
    if clause:
        yield clause


_FLOOD = r'\b(?:ngap|lut|lu quet|nuoc dang|nuoc len)\b'
_PEOPLE = r'\b(?:(?:nguoi|tre em|nguoi gia|gia dinh)[^;.!?]{0,60}?(?:mac ket|ket lai)|(?:mac ket|ket lai)[^;.!?]{0,60}?(?:nguoi|tre em|nguoi gia))\b'
_VEHICLES = r'\b(?:(?:xe|o to|xe may)[^;.!?]{0,60}?(?:mac ket|ket lai|chet may)|(?:mac ket|ket lai)[^;.!?]{0,60}?(?:xe|o to|xe may))\b'
_LIFE_THREAT = r'\b(?:duoi nuoc|chet duoi|nguy kich|bat tinh|(?:de doa|nguy hiem)(?: den)? tinh mang|(?:nguoi|tre em|em be)[^;.!?]{0,40}?(?:bi nuoc cuon|nuoc cuon troi|sap chim))\b'
_BREATHING_FAILURE = r'\b(?:khong the tho|khong tho duoc)\b'
# Only measurements attached to water/depth language, not any nearby road length,
# victim count or address. Signed/malformed values must not match a numeric tail.
_DEPTH = re.compile(r'\b(?:ngap|muc nuoc|do sau|nuoc cao|nuoc sau)\s+(?:(?:sau|cao|khoang|tam|toi|hon|gan|la|len|den)\s+)*(\d+(?:[.,]\d+)?)\s*(cm|m|met)\b(?![²³\d/])')


def extract(description):
    normalized = normalize(description)
    facts = []
    blocked = people = vehicles = emergency = flood = life_threat = False
    for clause in _clauses(description):
        text = '\x1e'.join(normalize(scope)['matchingText']
                             for scope in _CONTRAST.split(unicodedata.normalize('NFC', clause)))
        is_flood = positive(text, _FLOOD)
        is_blocked = positive(text, r'\b(?:duong (?:bi )?(?:chan|tac|chia cat)|cam duong)\b') or positive(
            text, r'\b(?:khong the (?:di|qua)|khong di (?:qua|duoc)|khong qua duoc)\b', inability=True)
        is_people = positive(text, _PEOPLE)
        is_vehicles = positive(text, _VEHICLES)
        is_life_threat = positive(text, _LIFE_THREAT) or positive(text, _BREATHING_FAILURE, inability=True)
        is_emergency = is_life_threat or positive(text, r'\b(?:cuu voi|can cuu ho|can cuu tro|mac ket|cap cuu|khan cap)\b')
        for kind, present in [('condition', is_flood), ('blocked_road', is_blocked),
                              ('stranded_people', is_people), ('stranded_vehicles', is_vehicles),
                              ('emergency', is_emergency), ('life_threat', is_life_threat)]:
            if present:
                facts.append({'kind': kind, 'text': clause})
        if is_flood:
            for match in _DEPTH.finditer(text):
                # Numeric evidence has its own polarity, including a denial later
                # in an otherwise positive flood clause.
                if not positive(text, re.escape(match.group())):
                    continue
                value = float(match[1].replace(',', '.'))
                if math.isfinite(value):
                    facts.append({'kind': 'depth', 'text': clause, 'value': value,
                                  'unit': 'cm' if match[2] == 'cm' else 'm'})
            if re.search(r'\b(?:dau goi|ngang (?:hong|bung|nguc)|chua ro do sau|khong ro do sau|khong biet do sau)\b', text):
                facts.append({'kind': 'depth', 'text': clause, 'value': None, 'unit': None})
        flood |= is_flood
        blocked |= is_blocked
        people |= is_people
        vehicles |= is_vehicles
        emergency |= is_emergency
        life_threat |= is_life_threat
    return {**normalized, 'facts': facts[:100], 'blockedRoad': blocked, 'strandedPeople': people,
            'strandedVehicles': vehicles, 'emergency': emergency, 'lifeThreat': life_threat,
            'hasFloodEvidence': flood,
            'ambiguousLocation': bool(re.search(r'\b(?:khong ro|khong biet) (?:vi tri|dia chi)\b', normalized['matchingText']))}


def cosine(a, b):
    if not a or len(a) != len(b) or not all(math.isfinite(v) for v in a + b):
        raise ValueError('Invalid vectors')
    # Scale first: finite provider/user values must not overflow or underflow
    # into a NaN score (which cannot be serialized as JSON).
    scale_a, scale_b = max(map(abs, a)), max(map(abs, b))
    if not scale_a or not scale_b:
        return 0.0
    unit_a, unit_b = [v / scale_a for v in a], [v / scale_b for v in b]
    norm = math.sqrt(sum(v*v for v in unit_a) * sum(v*v for v in unit_b))
    return max(-1.0, min(1.0, sum(x*y for x, y in zip(unit_a, unit_b)) / norm))
