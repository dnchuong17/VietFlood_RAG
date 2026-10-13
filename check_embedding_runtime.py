"""Small static paid embedding probe; never print provider bodies or credentials."""
import json
import sys
from pipeline_config import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
from rag_models import encode_dense


def main():
    try:
        vectors = encode_dense(['Kiểm tra kết nối VietFlood.'])
        if len(vectors) != 1:
            raise ValueError('Unexpected probe vector count')
        print(json.dumps({'stage': 'embedding', 'status': 'ready',
                          'model': EMBEDDING_MODEL, 'vectorSize': EMBEDDING_DIMENSIONS}))
        return 0
    except Exception as error:
        print(json.dumps({'stage': 'embedding', 'status': 'unavailable',
                          'errorType': type(error).__name__,
                          'httpStatus': getattr(error, 'status_code', None)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
