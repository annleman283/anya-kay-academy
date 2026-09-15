import hashlib,hmac,json,os,random,re,sqlite3,time,urllib.parse,urllib.request
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).parent; STATIC=BASE/'static'; DB_PATH=os.getenv('DB_PATH',str(BASE/'lessons.db'))
BOT_TOKEN=os.getenv('BOT_TOKEN',''); PORT=int(os.getenv('PORT','8080')); DEV_USER_ID=int(os.getenv('DEV_USER_ID','0') or 0)
PASS_THRESHOLD=float(os.getenv('PASS_THRESHOLD','1.0')); ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').replace(' ','').split(',') if x}

def conn():
 c=sqlite3.connect(DB_PATH,timeout=20); c.row_factory=sqlite3.Row; return c

def rows(sql,a=()):
 with conn() as c:return [dict(x) for x in c.execute(sql,a).fetchall()]
def row(sql,a=()):
 with conn() as c:
  x=c.execute(sql,a).fetchone(); return dict(x) if x else None
def db_ready():
 try:return bool(row("SELECT name FROM sqlite_master WHERE type='table' AND name='lessons'"))
 except:return False

def ensure_tables():
 if not db_ready():return
 with conn() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS academy_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,lesson_id INTEGER NOT NULL,note TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,lesson_id));
 CREATE TABLE IF NOT EXISTS academy_bookmarks(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,lesson_id INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,lesson_id));
 CREATE TABLE IF NOT EXISTS academy_final_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,score INTEGER NOT NULL,total INTEGER NOT NULL,passed INTEGER NOT NULL,finished_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS academy_profiles(user_id INTEGER PRIMARY KEY,full_name TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS academy_onboarding(user_id INTEGER PRIMARY KEY,completed INTEGER NOT NULL DEFAULT 0,completed_at TEXT);
 CREATE TABLE IF NOT EXISTS academy_schedule(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,event_date TEXT NOT NULL,event_time TEXT,title TEXT NOT NULL,notes TEXT,order_num INTEGER NOT NULL DEFAULT 1,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS academy_local_files(key TEXT PRIMARY KEY,original_name TEXT NOT NULL,stored_name TEXT NOT NULL,preview_name TEXT,mime_type TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
 ''')

def verify(raw):
 if not raw or not BOT_TOKEN:return None
 try:
  d=dict(urllib.parse.parse_qsl(raw,keep_blank_values=True)); got=d.pop('hash',''); check='\n'.join(f'{k}={v}' for k,v in sorted(d.items()))
  secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest(); want=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
  if not hmac.compare_digest(want,got) or int(time.time())-int(d.get('auth_date','0'))>86400:return None
  return json.loads(d.get('user','{}'))
 except:return None

def user(h):
 u=verify(h.get('X-Telegram-Init-Data',''))
 if u:return u
 if DEV_USER_ID:return {'id':DEV_USER_ID,'first_name':'Анна','username':'demo'}
 return {'id':0,'first_name':'Анна','username':'preview'}
def display_no(order):return max(0,int(order)-1)
def youtube_id(url):
 if not url:return ''
 m=re.search(r'(?:youtu\.be/|v=|embed/)([A-Za-z0-9_-]{6,})',url); return m.group(1) if m else ''
def shuffled_question(q):
 opts=json.loads(q['options']); random.shuffle(opts)
 return {'id':q['id'],'question_text':q['question_text'],'options':opts,'photo_file_id':q.get('photo_file_id'),'order_num':q.get('order_num')}

def bootstrap(uid,first):
 ls=rows('SELECT * FROM lessons ORDER BY order_num'); st=row('SELECT * FROM students WHERE user_id=?',(uid,)) if uid else None; current=int((st or {}).get('current_lesson_order',1))
 attempts=rows('SELECT * FROM attempts WHERE user_id=? ORDER BY finished_at',(uid,)) if uid else []; passed={a['lesson_id'] for a in attempts if a['passed']}
 for l in ls:
  o=int(l['order_num']); l['display_num']=display_no(o); l['state']='done' if l['id'] in passed or o<current else ('current' if o==current else 'locked')
 numbered=[l for l in ls if int(l['order_num'])>1]; completed=sum(1 for l in numbered if l['state']=='done'); total=len(numbered); pct=round(completed/total*100) if total else 0
 wrong=rows('''SELECT a.question_id,a.question_text,a.correct_text,l.id lesson_id,l.title lesson_title,COUNT(*) mistakes FROM answers a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND a.is_correct=0 GROUP BY a.question_id,a.question_text,a.correct_text,l.id,l.title ORDER BY mistakes DESC''',(uid,)) if uid else []
 prof=row('SELECT full_name FROM academy_profiles WHERE user_id=?',(uid,)) if uid else None; full=(prof or {}).get('full_name','')
 onboard=row('SELECT completed FROM academy_onboarding WHERE user_id=?',(uid,)) if uid else None
 finals=row('SELECT id FROM academy_final_attempts WHERE user_id=? AND passed=1 LIMIT 1',(uid,)) if uid else None
 schedule=rows('SELECT * FROM academy_schedule WHERE user_id=? ORDER BY event_date,event_time,order_num,id',(uid,)) if uid else []
 return {'mode':'live','telegram_ready':bool(BOT_TOKEN),'needs_profile':bool(uid and not full),'needs_onboarding':bool(uid and full and not (onboard or {}).get('completed')),'user':{'id':uid,'first_name':first,'full_name':full,'is_admin':uid in ADMIN_IDS},'progress':{'percent':pct,'completed':completed,'total':total,'current':current,'final_passed':bool(finals)},'lessons':ls,'mistakes':wrong,'bonus_materials':rows('SELECT * FROM bonus_materials ORDER BY order_num'),'schedule':schedule}

def media_url(fid):
 if str(fid).startswith(('http://','https://')):return str(fid)
 if not BOT_TOKEN:raise RuntimeError('Материал хранится в Telegram. Для него нужно подключить BOT_TOKEN учебного бота в Railway.')
 with urllib.request.urlopen(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={urllib.parse.quote(fid)}',timeout=10) as r:d=json.load(r)
 return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{d['result']['file_path']}"

def correct_text(q):return json.loads(q['options'])[int(q['correct_index'])]

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
 def redirect(self,url,download=None):
  self.send_response(302); self.send_header('Location',url)
  if download:self.send_header('Content-Disposition',f'attachment; filename="{download}"')
  self.end_headers()
 def html_error(self,msg,status=502):
  b=("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{font-family:Arial;background:#f4eee7;color:#241b1d;padding:28px}div{max-width:520px;margin:auto;background:white;padding:22px;border-radius:18px}h2{color:#64142b}</style><div><h2>Материал пока не открывается</h2><p>"+str(msg)+"</p><p>Вернись в Academy. После подключения Telegram-файлов эта кнопка будет работать.</p></div>").encode('utf-8')
  self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  p=urllib.parse.urlparse(self.path); uid,u=self.who()
  if p.path=='/health':return self.j({'ok':True,'db':db_ready(),'version':'2.3'})
  if p.path=='/api/bootstrap':return self.j(bootstrap(uid,u.get('first_name') or 'Ученица'))
  if p.path.startswith('/api/lesson/'):
   lid=int(p.path.rsplit('/',1)[-1]); l=row('SELECT * FROM lessons WHERE id=?',(lid,))
   if not l:return self.j({'error':'not_found'},404)
   l['display_num']=display_no(l['order_num']); l['youtube_id']=youtube_id(l.get('video_url',''))
   mats=rows('SELECT * FROM lesson_materials WHERE lesson_id=? ORDER BY order_num',(lid,))
   for m in mats:
    m['view_url']=f"/api/material/{m['id']}/view"; m['download_url']=f"/api/material/{m['id']}/download"
   l['materials']=mats
   qs=rows('SELECT id,question_text,options,photo_file_id,order_num FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,)); random.shuffle(qs); l['questions']=[shuffled_question(q) for q in qs]
   n=row('SELECT note FROM academy_notes WHERE user_id=? AND lesson_id=?',(uid,lid)) if uid else None; l['note']=(n or {}).get('note',''); l['bookmarked']=bool(row('SELECT id FROM academy_bookmarks WHERE user_id=? AND lesson_id=?',(uid,lid))) if uid else False
   return self.j(l)
  m=re.match(r'^/api/material/(\d+)/(view|download)$',p.path)
  if m:
   mat=row('SELECT * FROM lesson_materials WHERE id=?',(int(m.group(1)),)); action=m.group(2)
   if not mat:return self.j({'error':'Материал не найден'},404)
   fid=mat['file_id']
   if fid.startswith('local:'):
    f=row('SELECT * FROM academy_local_files WHERE key=?',(fid[6:],))
    if not f:return self.j({'error':'Файл не найден'},404)
    target=('previews/'+f['preview_name']) if action=='view' and f.get('preview_name') else ('materials/'+f['stored_name'])
    return self.redirect('/'+target)
   try:return self.redirect(media_url(fid))
   except Exception as e:return self.html_error(str(e))
  if p.path.startswith('/api/media/'):
   try:return self.redirect(media_url(urllib.parse.unquote(p.path.split('/api/media/',1)[1])))
   except Exception as e:return self.html_error(str(e))
  if p.path=='/api/saved':return self.j(rows('SELECT l.* FROM academy_bookmarks b JOIN lessons l ON l.id=b.lesson_id WHERE b.user_id=? ORDER BY b.created_at DESC',(uid,)) if uid else [])
  if p.path=='/api/notes':return self.j(rows('SELECT n.*,l.title,l.order_num FROM academy_notes n JOIN lessons l ON l.id=n.lesson_id WHERE n.user_id=? AND TRIM(n.note)<>"" ORDER BY n.updated_at DESC',(uid,)) if uid else [])
  if p.path=='/api/analytics':
   a=rows('''SELECT l.title,l.order_num,COUNT(a.id) attempts,MAX(CASE WHEN a.passed=1 THEN 1 ELSE 0 END) passed,MAX(CASE WHEN a.total>0 THEN ROUND(a.score*100.0/a.total) ELSE 0 END) best FROM lessons l LEFT JOIN attempts a ON a.lesson_id=l.id AND a.user_id=? GROUP BY l.id ORDER BY l.order_num''',(uid,)) if uid else []
   return self.j(a)
  if p.path=='/api/final/start':
   qs=rows('SELECT q.*,l.title lesson_title FROM questions q JOIN lessons l ON l.id=q.lesson_id WHERE l.order_num>1'); random.shuffle(qs); qs=qs[:min(40,len(qs))]
   return self.j({'questions':[dict(shuffled_question(q),lesson_title=q['lesson_title']) for q in qs]})
  if p.path=='/api/admin/overview':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   return self.j({'students':row('SELECT COUNT(*) n FROM students')["n"],'lessons':row('SELECT COUNT(*) n FROM lessons')["n"],'questions':row('SELECT COUNT(*) n FROM questions')["n"],'materials':row('SELECT COUNT(*) n FROM lesson_materials')["n"]+row('SELECT COUNT(*) n FROM bonus_materials')["n"]})
  if p.path=='/api/admin/students':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   return self.j(rows('SELECT s.*,p.full_name certificate_name FROM students s LEFT JOIN academy_profiles p ON p.user_id=s.user_id ORDER BY s.last_activity DESC'))
  if p.path.startswith('/api/admin/schedule/'):
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(p.path.rsplit('/',1)[-1]); return self.j(rows('SELECT * FROM academy_schedule WHERE user_id=? ORDER BY event_date,event_time,order_num,id',(sid,)))
  return super().do_GET()
 def do_POST(self):
  p=urllib.parse.urlparse(self.path).path; uid,u=self.who(); d=self.body()
  if not uid:return self.j({'error':'Открой приложение внутри Telegram для сохранения данных'},401)
  ensure_tables()
  if p=='/api/profile':
   name=' '.join(str(d.get('full_name','')).strip().split())
   if not re.fullmatch(r"[A-Za-z][A-Za-z'’-]+(?: [A-Za-z][A-Za-z'’-]+)+",name):return self.j({'error':'Введи имя и фамилию английскими буквами'},400)
   with conn() as c:c.execute('INSERT INTO academy_profiles(user_id,full_name) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name,updated_at=CURRENT_TIMESTAMP',(uid,name))
   return self.j({'ok':True,'full_name':name})
  if p=='/api/onboarding/complete':
   with conn() as c:c.execute('INSERT INTO academy_onboarding(user_id,completed,completed_at) VALUES(?,1,CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET completed=1,completed_at=CURRENT_TIMESTAMP',(uid,))
   return self.j({'ok':True})
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
   q=row('SELECT * FROM questions WHERE id=?',(int(d['question_id']),)); chosen=str(d.get('answer_text','')); ok=chosen==correct_text(q)
   return self.j({'correct':ok,'correct_text':correct_text(q),'explanation':q.get('explanation') or ''})
  if p=='/api/quiz/submit':
   lid=int(d['lesson_id']); given=d.get('answers',{}); qs=rows('SELECT * FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,)); out=[]; score=0
   for q in qs:
    ch=str(given.get(str(q['id']),'—')); ct=correct_text(q); ok=ch==ct; score+=int(ok); out.append({'question_id':q['id'],'question_text':q['question_text'],'chosen_text':ch,'correct_text':ct,'is_correct':ok,'explanation':q.get('explanation') or ''})
   passed=(score/len(qs)>=PASS_THRESHOLD) if qs else True
   with conn() as c:
    n=c.execute('SELECT COALESCE(MAX(attempt_number),0)+1 n FROM attempts WHERE user_id=? AND lesson_id=?',(uid,lid)).fetchone()['n']; cur=c.execute('INSERT INTO attempts(user_id,lesson_id,attempt_number,score,total,passed) VALUES(?,?,?,?,?,?)',(uid,lid,n,score,len(qs),int(passed))); aid=cur.lastrowid
    for a in out:c.execute('INSERT INTO answers(attempt_id,user_id,lesson_id,question_id,question_text,chosen_text,correct_text,is_correct) VALUES(?,?,?,?,?,?,?,?)',(aid,uid,lid,a['question_id'],a['question_text'],a['chosen_text'],a['correct_text'],int(a['is_correct'])))
    if passed:
     lo=c.execute('SELECT order_num FROM lessons WHERE id=?',(lid,)).fetchone()['order_num']; c.execute('UPDATE students SET current_lesson_order=MAX(current_lesson_order,?),last_activity=CURRENT_TIMESTAMP WHERE user_id=?',(lo+1,uid))
   return self.j({'score':score,'total':len(qs),'passed':passed,'answers':out})
  if p=='/api/lesson/complete':
   lid=int(d['lesson_id']); lo=row('SELECT order_num FROM lessons WHERE id=?',(lid,))['order_num']
   with conn() as c:c.execute('UPDATE students SET current_lesson_order=MAX(current_lesson_order,?),last_activity=CURRENT_TIMESTAMP WHERE user_id=?',(lo+1,uid))
   return self.j({'ok':True})
  if p=='/api/final/submit':
   given=d.get('answers',{}); score=0; total=0
   for k,ch in given.items():
    q=row('SELECT * FROM questions WHERE id=?',(int(k),)); total+=1; score+=int(str(ch)==correct_text(q))
   passed=bool(total and score/total>=PASS_THRESHOLD)
   with conn() as c:c.execute('INSERT INTO academy_final_attempts(user_id,score,total,passed) VALUES(?,?,?,?)',(uid,score,total,int(passed)))
   return self.j({'score':score,'total':total,'passed':passed})
  if p=='/api/admin/schedule/save':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(d['user_id']); eid=int(d.get('id') or 0); vals=(str(d['event_date']),str(d.get('event_time','')),str(d['title']).strip(),str(d.get('notes','')).strip(),int(d.get('order_num',1)))
   with conn() as c:
    if eid:c.execute('UPDATE academy_schedule SET event_date=?,event_time=?,title=?,notes=?,order_num=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',vals+(eid,sid))
    else:c.execute('INSERT INTO academy_schedule(user_id,event_date,event_time,title,notes,order_num) VALUES(?,?,?,?,?,?)',(sid,)+vals)
   return self.j({'ok':True})
  if p=='/api/admin/schedule/delete':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   with conn() as c:c.execute('DELETE FROM academy_schedule WHERE id=?',(int(d['id']),))
   return self.j({'ok':True})
  return self.j({'error':'not_found'},404)

if __name__=='__main__':
 ensure_tables(); print(f'ANYA KAY Academy v2.3 on :{PORT} | DB={DB_PATH}'); ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
