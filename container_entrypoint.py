"""Initialize persistent container data before running retrieval or preflight."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from filelock import FileLock
from pipeline_config import RAG_DATA_DIR
from corpus_storage import initialize_corpus
from runtime_diagnostics import error_details, stage

BOOTSTRAP_DIR = Path('/app/bootstrap')
MODEL_DIR = Path('/models')


def seed_artifacts():
    """Add image artifacts without overwriting any version already on the volume."""
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FileLock(str(RAG_DATA_DIR / 'sync.lock'), timeout=120):
        for kind in ('releases', 'snapshots'):
            source = BOOTSTRAP_DIR / kind
            if not source.exists():
                continue
            for item in sorted(source.rglob('*.json')):
                if item.is_symlink() or not item.is_file():
                    continue
                destination = RAG_DATA_DIR / kind / item.relative_to(source)
                if destination.exists():
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name('.seed-' + uuid.uuid4().hex)
                try:
                    shutil.copyfile(item, temporary)
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)


def prepare_volumes():
    """Explicit root-only maintenance command used before launching as app."""
    import pwd
    if os.geteuid() != 0:
        raise PermissionError('Volume preparation requires root')
    account = pwd.getpwnam('app')
    for root in (RAG_DATA_DIR, MODEL_DIR):
        if root.is_symlink():
            raise ValueError('Volume root must not be a symlink')
        root.mkdir(parents=True, exist_ok=True)
        paths = [root]
        for parent, directories, files in os.walk(root, followlinks=False):
            paths.extend(Path(parent) / name for name in directories + files)
        for path in paths:
            info = path.lstat()
            if path.is_symlink():
                continue
            if (info.st_uid, info.st_gid) != (account.pw_uid, account.pw_gid):
                os.chown(path, account.pw_uid, account.pw_gid)


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    try:
        if arguments == ['--prepare-volumes']:
            prepare_volumes()
            return 0
        release_modes = {'--prepare-release', '--check-release', '--publish-release', '--rollback-release'}
        if len(arguments) == 2 and arguments[0] == '--rollback-release':
            from deployment_release import rollback_release
            state = rollback_release(arguments[1])
            print(json.dumps({'event': 'deployment_rollback', 'status': state['status']}))
            return 0
        with stage('initialize_corpus'):
            seed_artifacts()
            initialize_corpus()
        if len(arguments) == 2 and arguments[0] in release_modes:
            for key in ('RAG_SERVICE_TOKEN', 'RAG_ADMIN_TOKEN', 'QDRANT_URL'):
                if not os.getenv(key, '').strip():
                    raise ValueError('Missing deployment configuration')
            from deployment_release import prepare_release, check_release, publish_release
            operation = {'--prepare-release': prepare_release, '--check-release': check_release,
                         '--publish-release': publish_release}[arguments[0]]
            with stage(arguments[0][2:]):
                state = operation(arguments[1])
            print(json.dumps({'event': 'deployment_release', 'operation': arguments[0],
                              'collection': state['collection'], 'status': state.get('status', 'ready')}))
            return 0
        if arguments == ['--check']:
            for key in ('RAG_SERVICE_TOKEN', 'RAG_ADMIN_TOKEN', 'QDRANT_URL'):
                if not os.getenv(key, '').strip():
                    raise ValueError('Missing deployment configuration')
            from retrieval_service import client, readiness
            try:
                ready = readiness()
                print(json.dumps({'event': 'deployment_preflight', **ready}))
            finally:
                client.close()
            return 0
        if not arguments:
            raise ValueError('Missing container command')
        os.execvp(arguments[0], arguments)
    except Exception as error:
        # Configuration/provider exceptions must not expose credentials.
        print(json.dumps({'event': 'container_initialization_failed',
                          **error_details(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
