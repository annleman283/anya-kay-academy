import hashlib, hmac, json, os, sqlite3, time, urllib.parse, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).parent
STATIC = BASE / 'static'
DB_PATH = os.getenv('DB_PATH', str(BASE / 'lessons.db'))
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
PORT = int(os.getenv('PORT', '8080'))
DEV_USER_ID = int(os.getenv('DEV_USER_ID', '0') or 0)


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def verify_init_data(raw):
    if not raw or not BOT_TOKEN:
        return None
    data = dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
    their_hash = data.pop('hash', '')
    check = '\n'.join(f'{k}={v}' for k,v in sorted(data.items()))
    secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
    ours = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(ours, their_hash): return None
    if int(time.time()) - int(data.get('auth_date','0')) > 86400: return None
    try: return json.loads(data.get('user','{}'))
    except Exception: return None


def user_from_headers(h):
    u = verify_init_data(h.get('X-Telegram-Init-Data',''))
    if u: return u
    if DEV_USER_ID: return {'id':DEV_USER_ID,'first_name':'Анна','username':'demo'}
    return {'id':0,'first_name':'Анна','username':'preview'}


def rows(sql,args=()):
    with conn() as c: return [dict(x) for x in c.execute(sql,args).fetchall()]

def row(sql,args=()):
    with conn() as c:
        x=c.execute(sql,args).fetchone(); return dict(x) if x else None


def demo_lessons():
    names=['Знакомство и организационные моменты','Строение ресниц','Материалы 1.0','Материалы 2.0','Организация рабочего места','Виды ресниц','Правила наращивания','Клей — часть 1','Клей — часть 2','Моделирование взгляда','Работа с рядами','Снятие ресниц','Коррекция ресниц','Ожог слизистой','Аллергия мастера и клиента','Стерилизация инструментов']
    return [{'id':i,'order_num':i,'title':n,'description':'Материалы урока ANYA KAY Academy','video_type':'link','video_url':'','video_file_id':None} for i,n in enumerate(names,1)]


def ensure_extra_tables():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS academy_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,lesson_id INTEGER,note TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,lesson_id));
        CREATE TABLE IF NOT EXISTS academy_bookmarks(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,lesson_id INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,lesson_id));
        ''')


def bootstrap(uid, first_name):
    lessons=rows('SELECT * FROM lessons ORDER BY order_num') if Path(DB_PATH).exists() else []
    if not lessons: lessons=demo_lessons()
    student=row('SELECT * FROM students WHERE user_id=?',(uid,)) if uid else None
    current=(student or {}).get('current_lesson_order',1)
    attempts=rows('SELECT * FROM attempts WHERE user_id=? ORDER BY finished_at',(uid,)) if uid else []
    passed={a['lesson_id'] for a in attempts if a['passed']}
    # Existing bot's canonical progression remains current_lesson_order.
    completed=max(0,min(len(lessons),current-1))
    pct=round(completed/len(lessons)*100) if lessons else 0
    for l in lessons:
        o=l['order_num']; l['state']='done' if o<current else ('current' if o==current else 'locked')
    wrong=rows('''SELECT a.question_id,a.question_text,a.correct_text,l.title lesson_title,COUNT(*) mistakes
                  FROM answers a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND a.is_correct=0
                  GROUP BY a.question_id,a.question_text,a.correct_text,l.title ORDER BY mistakes DESC''',(uid,)) if uid else []
    materials=rows('SELECT * FROM bonus_materials ORDER BY order_num') if Path(DB_PATH).exists() else []
    return {'user':{'id':uid,'first_name':first_name},'progress':{'percent':pct,'completed':completed,'total':len(lessons),'current':current},'lessons':lessons,'mistakes':wrong,'bonus_materials':materials}


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        clean=urllib.parse.urlparse(path).path
        if clean=='/': clean='/index.html'
        return str(STATIC / clean.lstrip('/'))
    def json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
    def body(self):
        n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        p=urllib.parse.urlparse(self.path)
        u=user_from_headers(self.headers); uid=int(u.get('id',0)); first=u.get('first_name') or 'Ученица'
        if p.path=='/api/bootstrap': return self.json(bootstrap(uid,first))
        if p.path.startswith('/api/lesson/'):
            lid=int(p.path.rsplit('/',1)[-1]); l=row('SELECT * FROM lessons WHERE id=?',(lid,))
            if not l: return self.json({'error':'not_found'},404)
            l['materials']=rows('SELECT * FROM lesson_materials WHERE lesson_id=? ORDER BY order_num',(lid,))
            qs=rows('SELECT id,question_text,options,explanation,photo_file_id,order_num FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,))
            for q in qs: q['options']=json.loads(q['options'])
            l['questions']=qs
            note=row('SELECT note FROM academy_notes WHERE user_id=? AND lesson_id=?',(uid,lid)) if uid else None
            l['note']=(note or {}).get('note','')
            l['bookmarked']=bool(row('SELECT id FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid))) if uid else False
            return self.json(l)
        if p.path.startswith('/api/media/'):
            fid=urllib.parse.unquote(p.path.split('/api/media/',1)[1])
            if not BOT_TOKEN: return self.json({'error':'BOT_TOKEN required'},503)
            try:
                with urllib.request.urlopen(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={urllib.parse.quote(fid)}') as r: data=json.load(r)
                fp=data['result']['file_path']; self.send_response(302); self.send_header('Location',f'https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}'); self.end_headers(); return
            except Exception as e: return self.json({'error':str(e)},502)
        return super().do_GET()
    def do_POST(self):
        p=urllib.parse.urlparse(self.path).path; u=user_from_headers(self.headers); uid=int(u.get('id',0)); data=self.body()
        if not uid: return self.json({'error':'Open inside Telegram for saving progress'},401)
        if p=='/api/note':
            with conn() as c: c.execute('INSERT INTO academy_notes(user_id,lesson_id,note) VALUES(?,?,?) ON CONFLICT(user_id,lesson_id) DO UPDATE SET note=excluded.note,updated_at=CURRENT_TIMESTAMP',(uid,int(data['lesson_id']),data.get('note','')))
            return self.json({'ok':True})
        if p=='/api/bookmark':
            lid=int(data['lesson_id'])
            with conn() as c:
                exists=c.execute('SELECT id FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid)).fetchone()
                if exists: c.execute('DELETE FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid)); state=False
                else: c.execute('INSERT INTO academy_bookmarks(user_id,lesson_id) VALUES(?,?)',(uid,lid)); state=True
            return self.json({'ok':True,'bookmarked':state})
        if p=='/api/quiz/submit':
            lid=int(data['lesson_id']); given=data.get('answers',{})
            qs=rows('SELECT * FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,))
            ans=[]; score=0
            for q in qs:
                opts=json.loads(q['options']); chosen=int(given.get(str(q['id']),-1)); ok=chosen==q['correct_index']; score+=int(ok)
                ans.append({'question_id':q['id'],'question_text':q['question_text'],'chosen_text':opts[chosen] if 0<=chosen<len(opts) else '—','correct_text':opts[q['correct_index']],'is_correct':ok,'explanation':q.get('explanation') if isinstance(q,dict) else q['explanation']})
            threshold=float(os.getenv('PASS_THRESHOLD','1.0')); passed=(score/len(qs)>=threshold) if qs else True
            with conn() as c:
                n=c.execute('SELECT COALESCE(MAX(attempt_number),0)+1 n FROM attempts WHERE user_id=? AND lesson_id=?',(uid,lid)).fetchone()['n']
                cur=c.execute('INSERT INTO attempts(user_id,lesson_id,attempt_number,score,total,passed) VALUES(?,?,?,?,?,?)',(uid,lid,n,score,len(qs),int(passed))); aid=cur.lastrowid
                for a in ans: c.execute('INSERT INTO answers(attempt_id,user_id,lesson_id,question_id,question_text,chosen_text,correct_text,is_correct) VALUES(?,?,?,?,?,?,?,?)',(aid,uid,lid,a['question_id'],a['question_text'],a['chosen_text'],a['correct_text'],int(a['is_correct'])))
                if passed:
                    lo=c.execute('SELECT order_num FROM lessons WHERE id=?',(lid,)).fetchone()['order_num']; c.execute('UPDATE students SET current_lesson_order=MAX(current_lesson_order,?) WHERE user_id=?',(lo+1,uid))
            return self.json({'score':score,'total':len(qs),'passed':passed,'answers':ans})
        return self.json({'error':'not_found'},404)

if __name__=='__main__':
    if Path(DB_PATH).exists(): ensure_extra_tables()
    print(f'ANYA KAY Academy Mini App: http://0.0.0.0:{PORT}')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
