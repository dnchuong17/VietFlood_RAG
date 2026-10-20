"""Credential-free deployment events and bounded, replay-safe Qdrant retries."""
from contextlib import contextmanager
import errno
import json
import socket
import ssl
import sys
import time

import httpx


def error_chain(error):
    pending, seen, chain = [error], set(), []
    while pending and len(chain) < 12:
        current = pending.pop(0)
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        # Qdrant stores the underlying HTTP error in .source.
        pending.extend([getattr(current, 'source', None), current.__cause__, current.__context__])
    return chain


def error_details(error):
    chain = error_chain(error)
    result = {'errorType': type(error).__name__, 'errorChain': [type(e).__name__ for e in chain]}
    for item in chain:
        code = getattr(item, 'status_code', None)
        if isinstance(code, int):
            result['httpStatus'] = code
        if isinstance(item, OSError) and isinstance(item.errno, int):
            result['errno'] = item.errno
    if any(isinstance(e, ssl.SSLCertVerificationError) for e in chain):
        result['category'] = 'tls_certificate'
    elif any(isinstance(e, socket.gaierror) for e in chain):
        result['category'] = 'dns'
    elif any(isinstance(e, (httpx.TimeoutException, TimeoutError)) for e in chain):
        result['category'] = 'timeout'
    elif any(isinstance(e, httpx.TransportError) for e in chain):
        result['category'] = 'transport'
    else:
        result['category'] = 'operation'
    # Never include exception text, request URLs, headers or response bodies.
    return result


def event(name, **fields):
    print(json.dumps({'event': name, **fields}), file=sys.stderr, flush=True)


@contextmanager
def stage(name):
    start = time.monotonic()
    event('deployment_stage_started', stage=name)
    try:
        yield
    except Exception as error:
        event('deployment_stage_failed', stage=name, elapsedSeconds=round(time.monotonic() - start, 2),
              **error_details(error))
        raise
    else:
        event('deployment_stage_completed', stage=name, elapsedSeconds=round(time.monotonic() - start, 2))


REPLAY_SAFE = {'get_aliases', 'collection_exists', 'get_collection', 'count', 'retrieve', 'upsert'}


def transient(error):
    chain = error_chain(error)
    if any(isinstance(e, ssl.SSLError) for e in chain):
        return False
    return any(isinstance(e, (httpx.TransportError, TimeoutError))
               or isinstance(e, OSError) and e.errno in {
                   errno.ECONNRESET, errno.ECONNREFUSED, errno.ETIMEDOUT, errno.EPIPE, socket.EAI_AGAIN}
               or getattr(e, 'status_code', None) in {502, 503, 504} for e in chain)


def qdrant_call(function, *args, **kwargs):
    operation = getattr(function, '__name__', 'unknown')
    attempts = 3 if operation in REPLAY_SAFE else 1
    for attempt in range(1, attempts + 1):
        start = time.monotonic()
        event('qdrant_request_started', operation=operation, attempt=attempt)
        try:
            result = function(*args, **kwargs)
        except Exception as error:
            retry = attempt < attempts and transient(error)
            event('qdrant_request_failed', operation=operation, attempt=attempt, retrying=retry,
                  elapsedSeconds=round(time.monotonic() - start, 2), **error_details(error))
            if not retry:
                raise
            time.sleep(2 ** attempt)
        else:
            event('qdrant_request_completed', operation=operation, attempt=attempt,
                  elapsedSeconds=round(time.monotonic() - start, 2))
            return result
