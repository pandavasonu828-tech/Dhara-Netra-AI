import os, sqlite3, hashlib, time, json, re, secrets
from difflib import SequenceMatcher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'dharanetra_lrms.sqlite3')

DEMO_CHAIN = [
    dict(record_id='LRMS-RAVI-001', parent_id=None, generation='Grandfather', owner_name='Rama Rao', survey_number='125', village='Bapatyapalli', mandal='Cot Bayyapalli', district='K.K. Dist.', area=20.0, land_type='Agricultural', transaction_type='Original Record', transaction_date='1995-06-08', document_number='18', status='HISTORICAL', latitude=15.9045, longitude=80.4548),
    dict(record_id='LRMS-RAVI-002', parent_id='LRMS-RAVI-001', generation='Father', owner_name='Suryanarayana', survey_number='125', village='Bapatyapalli', mandal='Cot Bayyapalli', district='K.K. Dist.', area=10.0, land_type='Agricultural', transaction_type='Family Transfer / Partition', transaction_date='2012-04-15', document_number='TR-2012-0415', status='HISTORICAL', latitude=15.9045, longitude=80.4548),
    dict(record_id='LRMS-RAVI-003', parent_id='LRMS-RAVI-002', generation='Current Holder', owner_name='Ravi Kumar', survey_number='125', village='Bapatyapalli', mandal='Cot Bayyapalli', district='K.K. Dist.', area=5.0, land_type='Agricultural', transaction_type='Family Transfer / Partition', transaction_date='2024-04-12', document_number='AP-2024-000123', status='CURRENT', latitude=15.9045, longitude=80.4548),
]

# Jury-demo ownership history for the Bengaluru test survey.
# IMPORTANT: a person's father/ancestor is NOT automatically a previous land
# owner. Only an explicit LRMS registration/transfer record belongs in the
# ownership history. The demo therefore contains one named previous registered
# holder and the current holder. The document's Father/Husband Name is shown
# separately by the UI as relationship context and is not used to infer title.
DEMO_CHAIN_HENNUR = [
    dict(record_id='LRMS-HENNUR-001', parent_id=None, generation='Previous Registered Holder', owner_name='Suryanarayana', survey_number='145/2A', village='Hennur Village', mandal='Yelahanka', district='Bengaluru Urban', area=5.0, land_type='Agricultural', transaction_type='Previous Registration Record (Demo)', transaction_date='2012-04-15', document_number='HN-2012-0415', status='HISTORICAL', latitude=13.030591, longitude=77.649317),
    dict(record_id='LRMS-HENNUR-002', parent_id='LRMS-HENNUR-001', generation='Current Holder', owner_name='Ravi Kumar', survey_number='145/2A', village='Hennur Village', mandal='Yelahanka', district='Bengaluru Urban', area=5.0, land_type='Agricultural', transaction_type='Transfer / Registration (Demo)', transaction_date='2024-04-12', document_number='HN-2024-000123', status='CURRENT', latitude=13.030591, longitude=77.649317),
]



def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS lrms_records (
      record_id TEXT PRIMARY KEY, parent_id TEXT, generation TEXT, owner_name TEXT,
      survey_number TEXT, village TEXT, mandal TEXT, district TEXT, area REAL,
      land_type TEXT, transaction_type TEXT, transaction_date TEXT, document_number TEXT,
      status TEXT, created_at REAL, latitude REAL, longitude REAL
    );
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT, event_time REAL, actor TEXT, action TEXT,
      record_id TEXT, details TEXT
    );
    CREATE TABLE IF NOT EXISTS document_registry (
      id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT, filename TEXT,
      record_id TEXT, uploaded_at REAL, field_signature TEXT, field_json TEXT
    );
    CREATE TABLE IF NOT EXISTS review_cases (
      case_id TEXT PRIMARY KEY, created_at REAL, updated_at REAL, status TEXT,
      source_filename TEXT, source_path TEXT, citizen_json TEXT, result_json TEXT,
      assigned_to TEXT, reviewed_by TEXT, review_remarks TEXT, decision TEXT,
      verified_record_id TEXT
    );
    ''')
    lrms_cols = {r[1] for r in conn.execute('PRAGMA table_info(lrms_records)').fetchall()}
    if 'latitude' not in lrms_cols: conn.execute('ALTER TABLE lrms_records ADD COLUMN latitude REAL')
    if 'longitude' not in lrms_cols: conn.execute('ALTER TABLE lrms_records ADD COLUMN longitude REAL')
    conn.execute("UPDATE lrms_records SET latitude=15.9045, longitude=80.4548 WHERE survey_number='125' AND latitude IS NULL")
    cols = {r[1] for r in conn.execute('PRAGMA table_info(document_registry)').fetchall()}
    if 'field_json' not in cols:
        conn.execute('ALTER TABLE document_registry ADD COLUMN field_json TEXT')
    # Migrate the earlier 145/2A demo lineage. The old version incorrectly
    # displayed unnamed 'Grandfather'/'Father' entries as if they were proven
    # land owners. Remove only those old demo rows and replace them with the
    # corrected ownership-history model.
    old_hennur=conn.execute(
        "SELECT record_id FROM lrms_records WHERE lower(survey_number)=lower(?) AND generation IN ('Grandfather','Father')",
        ('145/2A',)
    ).fetchall()
    if old_hennur:
        conn.execute("DELETE FROM lrms_records WHERE lower(survey_number)=lower(?)", ('145/2A',))

    existing_ids={r[0] for r in conn.execute('SELECT record_id FROM lrms_records').fetchall()}
    seeded_any=False
    for chain in (DEMO_CHAIN, DEMO_CHAIN_HENNUR):
        for r in chain:
            if r['record_id'] in existing_ids:
                continue
            conn.execute('''INSERT INTO lrms_records
              (record_id,parent_id,generation,owner_name,survey_number,village,mandal,district,area,land_type,transaction_type,transaction_date,document_number,status,created_at,latitude,longitude)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (*[r[k] for k in ['record_id','parent_id','generation','owner_name','survey_number','village','mandal','district','area','land_type','transaction_type','transaction_date','document_number','status']], time.time(), r.get('latitude'), r.get('longitude')))
            seeded_any=True
    if seeded_any:
        conn.execute('INSERT INTO audit_log(event_time,actor,action,record_id,details) VALUES (?,?,?,?,?)',
                     (time.time(),'SYSTEM','SEED_DEMO_LRMS','LRMS-HENNUR-002','Corrected demo LRMS ownership history initialized for Survey 145/2A; ancestors are not inferred as land owners.'))
    conn.commit(); conn.close()


def audit(action, record_id=None, details='', actor='DEMO OFFICER'):
    conn=db(); conn.execute('INSERT INTO audit_log(event_time,actor,action,record_id,details) VALUES (?,?,?,?,?)',
                            (time.time(),actor,action,record_id,details)); conn.commit(); conn.close()



def create_review_case(source_filename, source_path, citizen_data, result):
    """Persist a human-review case when the processing result needs attention."""
    flagged=[]
    conf=result.get('confidence') or {}
    comps=result.get('comparisons') or {}
    for k,v in conf.items():
        if isinstance(v,dict) and v.get('status') == 'NEEDS_REVIEW':
            flagged.append(k)
    for k,v in comps.items():
        if isinstance(v,dict) and v.get('status') == 'MISMATCH' and k not in flagged:
            flagged.append(k)
    if not flagged:
        return None
    case_id='RVW-'+secrets.token_hex(6).upper()
    now=time.time()
    payload=dict(result)
    payload['review_fields']=sorted(flagged)
    conn=db()
    conn.execute("""INSERT INTO review_cases
      (case_id,created_at,updated_at,status,source_filename,source_path,citizen_json,result_json)
      VALUES (?,?,?,?,?,?,?,?)""",
      (case_id,now,now,'PENDING',source_filename,source_path,
       json.dumps(citizen_data or {},ensure_ascii=False),json.dumps(payload,ensure_ascii=False)))
    conn.commit(); conn.close()
    return case_id


def review_cases(status=None):
    conn=db()
    if status:
        rows=conn.execute('SELECT * FROM review_cases WHERE status=? ORDER BY created_at DESC',(status,)).fetchall()
    else:
        rows=conn.execute('SELECT * FROM review_cases ORDER BY created_at DESC').fetchall()
    conn.close()
    out=[]
    for r in rows:
        item=dict(r)
        item.pop('source_path', None)
        for key in ('citizen_json','result_json'):
            try: item[key.replace('_json','')]=json.loads(item.pop(key) or '{}')
            except Exception: item[key.replace('_json','')]= {}
        try: item['review_fields']=item['result'].get('review_fields',[])
        except Exception: item['review_fields']=[]
        out.append(item)
    return out


def get_review_case(case_id):
    conn=db(); row=conn.execute('SELECT * FROM review_cases WHERE case_id=?',(case_id,)).fetchone(); conn.close()
    if not row: return None
    item=dict(row)
    item.pop('source_path', None)
    for key in ('citizen_json','result_json'):
        try: item[key.replace('_json','')]=json.loads(item.pop(key) or '{}')
        except Exception: item[key.replace('_json','')]= {}
    item['review_fields']=item['result'].get('review_fields',[])
    return item


def decide_review_case(case_id, decision, fields=None, reviewer='', remarks=''):
    case=get_review_case(case_id)
    if not case: return None
    if case['status'] != 'PENDING': return case
    result=case['result'] or {}
    if decision == 'APPROVED':
        final_fields=result.get('fields') or {}
    elif decision == 'CORRECTED':
        final_fields=dict(result.get('fields') or {})
        for k,v in (fields or {}).items():
            if str(v).strip(): final_fields[k]=str(v).strip()
        result['fields']=final_fields
    else:
        raise ValueError('Decision must be APPROVED or CORRECTED.')
    rid='DHR-'+secrets.token_hex(4).upper()
    result['verified_record_id']=rid
    result['review_decision']=decision
    result['reviewed_by']=reviewer
    result['review_remarks']=remarks
    now=time.time()
    conn=db(); conn.execute("""UPDATE review_cases SET updated_at=?,status=?,reviewed_by=?,review_remarks=?,decision=?,verified_record_id=?,result_json=? WHERE case_id=?""",
      (now,'APPROVED',reviewer,remarks,decision,rid,json.dumps(result,ensure_ascii=False),case_id)); conn.commit(); conn.close()
    audit('OFFICER_REVIEW_'+decision,rid,f'case={case_id}; source={case["source_filename"]}; remarks={remarks}',actor=f'OFFICER:{reviewer}')
    return get_review_case(case_id)

def all_records():
    conn=db(); rows=[dict(r) for r in conn.execute('SELECT * FROM lrms_records ORDER BY transaction_date ASC, created_at ASC')]; conn.close(); return rows


def search_records(survey_number='', owner_name=''):
    conn=db()
    rows=conn.execute('''SELECT * FROM lrms_records WHERE (?='' OR lower(survey_number)=lower(?)) AND (?='' OR lower(owner_name) LIKE '%'||lower(?)||'%') ORDER BY transaction_date ASC''',
                      (survey_number,survey_number,owner_name,owner_name)).fetchall()
    conn.close(); return [dict(r) for r in rows]


def chain(survey_number):
    rows=search_records(survey_number=survey_number)
    by_id={r['record_id']:r for r in rows}
    # If exact survey query is empty, return nothing; otherwise order by history.
    return rows


def _norm(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def field_signature(fields):
    keys=['survey_number','village','mandal','district','owner_name','extent','land_type']
    values={k:str(fields.get(k,'')).strip() for k in keys}
    raw='|'.join(_norm(values[k]) for k in keys)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _field_payload(fields):
    keys=['survey_number','village','mandal','district','owner_name','extent','land_type']
    return {k:str(fields.get(k,'')).strip() for k in keys}


def register_document(file_path, filename, record_id=None, fields=None):
    with open(file_path,'rb') as f: digest=hashlib.sha256(f.read()).hexdigest()
    payload=_field_payload(fields or {})
    sig=field_signature(fields or {})
    conn=db()
    existing=conn.execute('SELECT * FROM document_registry WHERE file_hash=? ORDER BY id ASC LIMIT 1', (digest,)).fetchone()
    if not existing:
        conn.execute('INSERT INTO document_registry(file_hash,filename,record_id,uploaded_at,field_signature,field_json) VALUES (?,?,?,?,?,?)',
                     (digest,filename,record_id,time.time(),sig,json.dumps(payload,ensure_ascii=False)))
        conn.commit()
    conn.close()
    return {'sha256':digest,'exact_duplicate':bool(existing),'existing':dict(existing) if existing else None}


def _similarity(candidate, existing):
    weights={'survey_number':2.2,'owner_name':1.8,'village':1.2,'mandal':1.0,'district':1.0,'extent':1.3,'land_type':0.8}
    score=0.0; total=0.0; matched=[]
    for k,w in weights.items():
        a=_norm(candidate.get(k,'')); b=_norm(existing.get(k,''))
        if not a and not b: continue
        total += w
        ratio=SequenceMatcher(None,a,b).ratio() if a and b else 0.0
        score += ratio*w
        if a and b and ratio >= 0.95: matched.append(k)
    return (score/total*100 if total else 0.0), matched


def duplicate_candidates(file_path, fields):
    reg=register_document(file_path, os.path.basename(file_path), fields=fields)
    conn=db(); rows=conn.execute('SELECT * FROM document_registry ORDER BY uploaded_at DESC').fetchall(); conn.close()
    candidates=[]
    current_hash=reg['sha256']
    for row in rows:
        if row['file_hash'] == current_hash: continue
        raw=row['field_json'] if 'field_json' in row.keys() else None
        if not raw: continue
        try: existing=json.loads(raw)
        except Exception: continue
        similarity, matched=_similarity(fields or {}, existing)
        if similarity >= 70:
            item=dict(row)
            item['similarity']=round(similarity,1)
            item['matched_fields']=matched
            item['duplicate_type']='EXACT_FIELD_DUPLICATE' if similarity >= 99.9 else 'SIMILAR_RECORD_REVIEW'
            candidates.append(item)
    candidates.sort(key=lambda x:x['similarity'], reverse=True)
    return reg, candidates[:10]

def link_candidate(fields):
    survey=str(fields.get('survey_number') or '').strip()
    owner=str(fields.get('owner_name') or '').strip()
    if not survey: return {'linked':False,'reason':'Survey number is required to locate the LRMS history.','matches':[]}
    rows=search_records(survey_number=survey)
    if not rows: return {'linked':False,'reason':'No matching survey number found in the prototype LRMS registry.','matches':[]}
    scored=[]
    for r in rows:
        score=0
        if owner and owner.lower() == str(r['owner_name']).lower(): score += 50
        if str(fields.get('village','')).lower() == str(r['village']).lower(): score += 20
        if str(fields.get('district','')).lower() == str(r['district']).lower(): score += 15
        if fields.get('extent'):
            import re
            m=re.search(r'\d+(?:\.\d+)?',str(fields.get('extent'))); a=float(m.group()) if m else None
            if a is not None and abs(a-float(r['area']))<1e-9: score += 15
        scored.append((score,r))
    scored.sort(key=lambda x:(x[0], x[1]['transaction_date']), reverse=True)
    return {'linked':True,'best_match':scored[0][1],'match_score':scored[0][0],'matches':[r for _,r in scored]}


def append_record_from_verified(fields, transaction_type='Verified Update', parent_id=None, actor='DEMO OFFICER'):
    survey=str(fields.get('survey_number') or '').strip()
    if not survey: raise ValueError('Survey number is required.')
    import re
    m=re.search(r'\d+(?:\.\d+)?',str(fields.get('extent') or ''))
    area=float(m.group()) if m else None
    rec_id='LRMS-'+hashlib.sha1(f"{survey}|{fields.get('owner_name')}|{time.time()}".encode()).hexdigest()[:10].upper()
    conn=db()
    # Carry forward the survey's known GIS anchor when a verified document does
    # not itself contain coordinates. This keeps GIS linked to the same survey
    # instead of losing the map after a new verified record is created.
    anchor=conn.execute('SELECT latitude, longitude FROM lrms_records WHERE lower(survey_number)=lower(?) AND latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY transaction_date DESC, created_at DESC LIMIT 1',(survey,)).fetchone()
    lat=fields.get('latitude') if fields.get('latitude') is not None else (anchor['latitude'] if anchor else None)
    lon=fields.get('longitude') if fields.get('longitude') is not None else (anchor['longitude'] if anchor else None)
    conn.execute('''INSERT INTO lrms_records(record_id,parent_id,generation,owner_name,survey_number,village,mandal,district,area,land_type,transaction_type,transaction_date,document_number,status,created_at,latitude,longitude)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (rec_id,parent_id,'Verified Update',fields.get('owner_name'),survey,fields.get('village'),fields.get('mandal'),fields.get('district'),area,fields.get('land_type'),transaction_type,fields.get('date') or time.strftime('%Y-%m-%d'),fields.get('document_number'),'CURRENT',time.time(),lat,lon)); conn.commit(); conn.close()
    audit('CREATE_VERIFIED_LRMS_RECORD',rec_id,f'Created from verified document for survey {survey}.',actor)
    return rec_id


def audit_events(limit=100):
    conn=db(); rows=conn.execute('SELECT * FROM audit_log ORDER BY event_time DESC LIMIT ?', (int(limit),)).fetchall(); conn.close(); return [dict(r) for r in rows]


def gis_parcel(survey_number):
    rows=search_records(survey_number=survey_number)
    if not rows:
        return {'survey_number':survey_number,'found':False,'history':[],'parcel':None,'demo_geometry':False}
    geo_rows=[r for r in rows if r.get('latitude') is not None and r.get('longitude') is not None]
    latest=rows[-1]
    geo_latest=geo_rows[-1] if geo_rows else latest
    lat=geo_latest.get('latitude'); lon=geo_latest.get('longitude')
    return {
        'survey_number':survey_number,
        'found':True,
        'parcel':{
            'name':f"Survey {survey_number}",
            'area':latest.get('area'),
            'latitude':lat,
            'longitude':lon,
            'source':'LRMS-linked coordinate anchor',
        },
        'history_available_in':'LRMS History',
        'demo_geometry':False,
    }

init_db()
