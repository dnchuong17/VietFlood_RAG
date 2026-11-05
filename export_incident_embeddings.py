"""Embed only the synthetic incident benchmark using the existing model client."""
import json
import sys
from incident_processing import extract, PIPELINE, embedding_text, incident_embedding_fingerprint
from rag_models import encode_dense, embedding_fingerprint


def main():
    with open(sys.argv[1], encoding='utf-8') as stream:
        dataset = json.load(stream)
    texts = list(dict.fromkeys(report['description'] for case in dataset['cases']
                             for report in [case['report'], case['candidate'], *([case['runnerUp']] if 'runnerUp' in case else [])]))
    analyses = [extract(text) for text in texts]
    embeddings = encode_dense([embedding_text(item) for item in analyses])
    fingerprint = incident_embedding_fingerprint(embedding_fingerprint())
    output = {'analyses': {text: {**analysis, 'embedding': vector, 'fingerprint': fingerprint, 'pipeline': PIPELINE}
                           for text, analysis, vector in zip(texts, analyses, embeddings, strict=True)}}
    with open(sys.argv[2], 'w', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False)
    print(json.dumps({'embeddedDescriptions': len(texts), 'fingerprint': fingerprint}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Incident benchmark embeddings failed ({type(exc).__name__}); inspect model configuration and access.', file=sys.stderr)
        sys.exit(1)
