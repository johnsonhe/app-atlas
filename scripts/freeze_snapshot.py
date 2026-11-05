"""Freeze verified collection results into portable compressed source records."""
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import store

with store.connect() as db:
    tables = {name:[dict(r) for r in db.execute(f"SELECT * FROM {name} ORDER BY id")] for name in ("apps","reviews")}
for name, rows in tables.items():
    with gzip.open(store.DATA / (name+'.jsonl.gz'),'wt',encoding='utf-8',compresslevel=9) as f:
        for r in rows:
            f.write(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n')
p=store.DATA/'manifest.json'
d=json.loads(p.read_text())
d.update(built_at=datetime.now(timezone.utc).isoformat(),apps=len(tables['apps']),reviews=len(tables['reviews']),
         identified_reviews=sum(bool(r['app_id']) for r in tables['reviews']),pooled_reviews=sum(not r['app_id'] for r in tables['reviews']))
d['files']={name+'.jsonl.gz':{'bytes':(store.DATA/(name+'.jsonl.gz')).stat().st_size,'sha256':hashlib.sha256((store.DATA/(name+'.jsonl.gz')).read_bytes()).hexdigest()} for name in tables}
d['mendeley_audit']['original_data_rows']=sum(d['mendeley_audit']['rejected'].values())+d['mendeley_audit']['retained_reviews']
p.write_text(json.dumps(d,indent=2)+'\n')
print({k:d[k] for k in ('apps','reviews','identified_reviews','pooled_reviews')})
