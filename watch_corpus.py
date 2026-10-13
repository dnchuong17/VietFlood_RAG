"""Poll approved source files; sync edits/additions/deletions with a debounce."""
import hashlib,subprocess,sys,time
from pipeline_config import MARKDOWN_DIR,PROJECT_ROOT

def fingerprint():
    return hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sorted(MARKDOWN_DIR.glob('*.md')))).hexdigest()
if __name__=='__main__':
    previous=None
    while True:
        current=fingerprint()
        if current!=previous:
            time.sleep(2)
            if fingerprint()!=current: continue
            result=subprocess.run([sys.executable,'sync_pipeline.py'],cwd=PROJECT_ROOT)
            if result.returncode==0: previous=current
        time.sleep(3)
