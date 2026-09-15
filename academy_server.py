import hashlib, hmac, json, os, random, sqlite3, time, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).parent; STATIC=BASE/'static'
DB_PATH=os.getenv('DB_PATH',str(BASE/'lessons.db')); BOT_TOKEN=os.getenv('BOT_TOKEN','')
PORT=int(os.getenv('PORT','8080')); DEV_USER_ID=int(os.getenv('DEV_USER_ID','0') or 0)
PASS_THRESHOLD=float(os.getenv('PASS_THRESHOLD','1.0')); ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').replace(' ','').split(',') if x}

def conn():
    c=sqlite3.connect(DB_PATH,timeout=20); c.row_factory=sqlite3.Row; return c

def db_ready():
    try:
        with conn() as c: return bool(c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lessons'").fetchone())
    except Exception:return False

def ensure_tables():
    if not db_ready(): return
    with conn() as c:c.executescript('''
    CREATE TABLE IF NOT EXISTS academy_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,lesson_id INTEGER NOT NULL,note TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,lesson_id));
    CREATE TABLE IF NOT EXISTS academy_bookmarks(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,lesson_id INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,lesson_id));
    CREATE TABLE IF NOT EXISTS academy_final_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,score INTEGER NOT NULL,total INTEGER NOT NULL,passed INTEGER NOT NULL,finished_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')

def verify(raw):
    if not raw or not BOT_TOKEN:return None
    try:
        d=dict(urllib.parse.parse_qsl(raw,keep_blank_values=True)); got=d.pop('hash',''); check='\n'.join(f'{k}={v}' for k,v in sorted(d.items()))
        secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest(); want=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want,got):return None
        if int(time.time())-int(d.get('auth_date','0'))>86400:return None
        return json.loads(d.get('user','{}'))
    except Exception:return None

def user(h):
    u=verify(h.get('X-Telegram-Init-Data',''))
    if u:return u
    if DEV_USER_ID:return {'id':DEV_USER_ID,'first_name':'Анна','username':'demo'}
    return {'id':0,'first_name':'Анна','username':'preview'}

def rows(sql,a=()):
    with conn() as c:return [dict(x) for x in c.execute(sql,a).fetchall()]
def row(sql,a=()):
    with conn() as c:
        x=c.execute(sql,a).fetchone(); return dict(x) if x else None

def demo():
    names=['Знакомство','Строение и фазы роста ресниц','Стартовый набор мастера','Организация рабочего места','Пинцеты и виды ресниц','Классика и объём','Препараты','Работа с клеем','Изоляция нижних ресниц','Подготовка, постановка и отступ','Склейки и направление','Методы наращивания и пучок','Работа с рядами','Моделирование взгляда','Снятие и коррекция','Ожог. Аллергия. Здоровье мастера']
    return [{'id':i,'order_num':i,'title':n,'description':'Урок ANYA KAY Academy','video_type':'link','video_url':'','video_file_id':None} for i,n in enumerate(names,1)]

def display_no(order): return max(0,int(order)-1)
def bootstrap(uid,first):
    live=db_ready(); ls=rows('SELECT * FROM lessons ORDER BY order_num') if live else demo()
    st=row('SELECT * FROM students WHERE user_id=?',(uid,)) if live and uid else None; current=int((st or {}).get('current_lesson_order',1))
    attempts=rows('SELECT * FROM attempts WHERE user_id=? ORDER BY finished_at',(uid,)) if live and uid else []
    passed={a['lesson_id'] for a in attempts if a['passed']}
    for l in ls:
        o=int(l['order_num']); l['display_num']=display_no(o); l['state']='done' if o<current else ('current' if o==current else 'locked')
    # Lesson 0 is orientation and is not counted in numbered course lessons.
    numbered=[l for l in ls if int(l['order_num'])>1]; completed=sum(1 for l in numbered if l['state']=='done'); total=len(numbered); pct=round(completed/total*100) if total else 0
    wrong=rows('''SELECT a.question_id,a.question_text,a.correct_text,l.id lesson_id,l.title lesson_title,COUNT(*) mistakes FROM answers a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND a.is_correct=0 GROUP BY a.question_id,a.question_text,a.correct_text,l.id,l.title ORDER BY mistakes DESC''',(uid,)) if live and uid else []
    mats=rows('SELECT * FROM bonus_materials ORDER BY order_num') if live else []
    finals=row('SELECT * FROM academy_final_attempts WHERE user_id=? AND passed=1 ORDER BY finished_at DESC LIMIT 1',(uid,)) if live and uid else None
    return {'mode':'live' if live else 'preview','user':{'id':uid,'first_name':first,'is_admin':uid in ADMIN_IDS},'progress':{'percent':pct,'completed':completed,'total':total,'current':current,'final_passed':bool(finals)},'lessons':ls,'mistakes':wrong,'bonus_materials':mats}

def media_url(fid):
    if not BOT_TOKEN:return None
    with urllib.request.urlopen(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={urllib.parse.quote(fid)}',timeout=10) as r:d=json.load(r)
    return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{d['result']['file_path']}"

class H(SimpleHTTPRequestHandler):
    def translate_path(self,p):
        clean=urllib.parse.urlparse(p).path
        if clean=='/':clean='/index.html'
        return str(STATIC/clean.lstrip('/'))
    def j(self,o,s=200):
        b=json.dumps(o,ensure_ascii=False).encode(); self.send_response(s); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def body(self):
        try:return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
        except:return {}
    def who(self):
        u=user(self.headers); return int(u.get('id',0)),u
    def do_GET(self):
        p=urllib.parse.urlparse(self.path); uid,u=self.who()
        if p.path=='/health':return self.j({'ok':True,'db':db_ready()})
        if p.path=='/api/bootstrap':return self.j(bootstrap(uid,u.get('first_name') or 'Ученица'))
        if p.path.startswith('/api/lesson/'):
            lid=int(p.path.rsplit('/',1)[-1]); live=db_ready(); l=row('SELECT * FROM lessons WHERE id=?',(lid,)) if live else next((x for x in demo() if x['id']==lid),None)
            if not l:return self.j({'error':'not_found'},404)
            l['display_num']=display_no(l['order_num'])
            l['materials']=rows('SELECT * FROM lesson_materials WHERE lesson_id=? ORDER BY order_num',(lid,)) if live else []
            qs=rows('SELECT id,question_text,options,explanation,photo_file_id,order_num FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,)) if live else []
            for q in qs:q['options']=json.loads(q['options'])
            l['questions']=qs
            n=row('SELECT note FROM academy_notes WHERE user_id=? AND lesson_id=?',(uid,lid)) if live and uid else None; l['note']=(n or {}).get('note','')
            l['bookmarked']=bool(row('SELECT id FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid))) if live and uid else False
            return self.j(l)
        if p.path.startswith('/api/media/'):
            try:self.send_response(302); self.send_header('Location',media_url(urllib.parse.unquote(p.path.split('/api/media/',1)[1]))); self.end_headers(); return
            except Exception as e:return self.j({'error':str(e)},502)
        if p.path=='/api/saved':
            if not db_ready() or not uid:return self.j([])
            return self.j(rows('SELECT l.* FROM academy_bookmarks b JOIN lessons l ON l.id=b.lesson_id WHERE b.user_id=? ORDER BY b.created_at DESC',(uid,)))
        if p.path=='/api/notes':
            if not db_ready() or not uid:return self.j([])
            return self.j(rows('SELECT n.*,l.title,l.order_num FROM academy_notes n JOIN lessons l ON l.id=n.lesson_id WHERE n.user_id=? AND TRIM(n.note)<>"" ORDER BY n.updated_at DESC',(uid,)))
        if p.path=='/api/analytics':
            if not db_ready() or not uid:return self.j([])
            a=rows('''SELECT l.title,l.order_num,COUNT(a.id) attempts,MAX(CASE WHEN a.passed=1 THEN 1 ELSE 0 END) passed,MAX(CASE WHEN a.total>0 THEN ROUND(a.score*100.0/a.total) ELSE 0 END) best FROM lessons l LEFT JOIN attempts a ON a.lesson_id=l.id AND a.user_id=? GROUP BY l.id ORDER BY l.order_num''',(uid,))
            for x in a:x['display_num']=display_no(x['order_num'])
            return self.j(a)
        if p.path=='/api/final/start':
            if not db_ready():return self.j({'questions':[]})
            qs=rows('SELECT q.id,q.question_text,q.options,q.photo_file_id,l.title lesson_title FROM questions q JOIN lessons l ON l.id=q.lesson_id WHERE l.order_num>1')
            random.shuffle(qs); qs=qs[:min(40,len(qs))]
            for q in qs:q['options']=json.loads(q['options'])
            return self.j({'questions':qs})
        return super().do_GET()
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path; uid,u=self.who(); d=self.body()
        if not uid:return self.j({'error':'Открой приложение внутри Telegram для сохранения данных'},401)
        if not db_ready():return self.j({'error':'База курса ещё не подключена'},503)
        ensure_tables()
        if p=='/api/note':
            with conn() as c:c.execute('INSERT INTO academy_notes(user_id,lesson_id,note) VALUES(?,?,?) ON CONFLICT(user_id,lesson_id) DO UPDATE SET note=excluded.note,updated_at=CURRENT_TIMESTAMP',(uid,int(d['lesson_id']),d.get('note','')))
            return self.j({'ok':True})
        if p=='/api/bookmark':
            lid=int(d['lesson_id'])
            with conn() as c:
                x=c.execute('SELECT id FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid)).fetchone()
                if x:c.execute('DELETE FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid)); state=False
                else:c.execute('INSERT INTO academy_bookmarks(user_id,lesson_id) VALUES(?,?)',(uid,lid)); state=True
            return self.j({'ok':True,'bookmarked':state})
        if p=='/api/quiz/check':
            q=row('SELECT * FROM questions WHERE id=?',(int(d['question_id']),)); idx=int(d.get('answer',-1)); opts=json.loads(q['options']); ok=idx==int(q['correct_index'])
            return self.j({'correct':ok,'correct_text':opts[int(q['correct_index'])],'explanation':q.get('explanation') or ''})
        if p=='/api/quiz/submit':
            lid=int(d['lesson_id']); given=d.get('answers',{}); qs=rows('SELECT * FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,)); out=[]; score=0
            for q in qs:
                opts=json.loads(q['options']); ch=int(given.get(str(q['id']),-1)); ok=ch==int(q['correct_index']); score+=int(ok); out.append({'question_id':q['id'],'question_text':q['question_text'],'chosen_text':opts[ch] if 0<=ch<len(opts) else '—','correct_text':opts[int(q['correct_index'])],'is_correct':ok,'explanation':q.get('explanation') or ''})
            passed=(score/len(qs)>=PASS_THRESHOLD) if qs else True
            with conn() as c:
                n=c.execute('SELECT COALESCE(MAX(attempt_number),0)+1 n FROM attempts WHERE user_id=? AND lesson_id=?',(uid,lid)).fetchone()['n']; cur=c.execute('INSERT INTO attempts(user_id,lesson_id,attempt_number,score,total,passed) VALUES(?,?,?,?,?,?)',(uid,lid,n,score,len(qs),int(passed))); aid=cur.lastrowid
                for a in out:c.execute('INSERT INTO answers(attempt_id,user_id,lesson_id,question_id,question_text,chosen_text,correct_text,is_correct) VALUES(?,?,?,?,?,?,?,?)',(aid,uid,lid,a['question_id'],a['question_text'],a['chosen_text'],a['correct_text'],int(a['is_correct'])))
                if passed:
                    lo=c.execute('SELECT order_num FROM lessons WHERE id=?',(lid,)).fetchone()['order_num']; c.execute('UPDATE students SET current_lesson_order=MAX(current_lesson_order,?),last_activity=CURRENT_TIMESTAMP WHERE user_id=?',(lo+1,uid))
            return self.j({'score':score,'total':len(qs),'passed':passed,'answers':out})
        if p=='/api/final/submit':
            given=d.get('answers',{}); ids=[int(x) for x in given.keys()]
            if not ids:return self.j({'score':0,'total':0,'passed':False})
            marks=[]; score=0
            for qid in ids:
                q=row('SELECT * FROM questions WHERE id=?',(qid,)); ch=int(given[str(qid)]); ok=ch==int(q['correct_index']); score+=int(ok); marks.append(ok)
            passed=score/len(ids)>=PASS_THRESHOLD
            with conn() as c:c.execute('INSERT INTO academy_final_attempts(user_id,score,total,passed) VALUES(?,?,?,?)',(uid,score,len(ids),int(passed)))
            return self.j({'score':score,'total':len(ids),'passed':passed})
        return self.j({'error':'not_found'},404)

if __name__=='__main__':
    ensure_tables(); print(f'ANYA KAY Academy on :{PORT} | DB={DB_PATH} | ready={db_ready()}'); ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
