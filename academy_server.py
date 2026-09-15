import base64,hashlib,hmac,json,mimetypes,os,random,re,sqlite3,time,urllib.parse,urllib.request,uuid
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path

BASE=Path(__file__).parent; STATIC=BASE/'static'; DB_PATH=os.getenv('DB_PATH',str(BASE/'lessons.db'))
BOT_TOKEN=os.getenv('BOT_TOKEN',''); PORT=int(os.getenv('PORT','8080')); DEV_USER_ID=int(os.getenv('DEV_USER_ID','0') or 0)
MEDIA_DIR=Path(os.getenv('MEDIA_DIR',str(BASE/'runtime_media'))); MEDIA_DIR.mkdir(parents=True,exist_ok=True)
FINAL_PASS_THRESHOLD=0.70
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
 CREATE TABLE IF NOT EXISTS academy_exam_questions(id INTEGER PRIMARY KEY AUTOINCREMENT,question_text TEXT NOT NULL,options TEXT NOT NULL,correct_index INTEGER NOT NULL,order_num INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS academy_admin_notes(user_id INTEGER PRIMARY KEY,note TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
 CREATE TABLE IF NOT EXISTS academy_lesson_settings(lesson_id INTEGER PRIMARY KEY,published INTEGER NOT NULL DEFAULT 1);
 CREATE TABLE IF NOT EXISTS academy_material_unlock(material_id INTEGER PRIMARY KEY,unlock_mode TEXT NOT NULL DEFAULT 'always');
 ''')
 with conn() as c:
  # Safe content correction only: does not reset students, attempts, answers or progress.
  c.execute("UPDATE questions SET question_text=REPLACE(question_text,'изгиб Л','изгиб L') WHERE question_text LIKE '%изгиб Л%'")
  n=c.execute('SELECT COUNT(*) n FROM academy_exam_questions').fetchone()['n']
  if not n:
   try:
    exam=json.loads((BASE/'final_exam.json').read_text(encoding='utf-8'))
    for q in exam:c.execute('INSERT INTO academy_exam_questions(question_text,options,correct_index,order_num) VALUES(?,?,?,?)',(q['question'],json.dumps(q['options'],ensure_ascii=False),int(q['correct_index']),int(q['number'])))
   except Exception as e:print('exam init error',e)

def verify_detail(raw):
 if not raw:return None,'initData отсутствует'
 if not BOT_TOKEN:return None,'BOT_TOKEN отсутствует на сервере Academy'
 try:
  d=dict(urllib.parse.parse_qsl(raw,keep_blank_values=True)); got=d.pop('hash','')
  if not got:return None,'В initData нет hash'
  check='\n'.join(f'{k}={v}' for k,v in sorted(d.items()))
  secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest(); want=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
  if not hmac.compare_digest(want,got):return None,'initData пришёл, но подпись не прошла проверку — BOT_TOKEN Academy не соответствует боту, который открыл Mini App'
  auth=int(d.get('auth_date','0') or 0)
  if auth and int(time.time())-auth>86400:return None,'Telegram initData старше 24 часов — полностью закрой и заново открой Mini App'
  u=json.loads(d.get('user','{}'))
  if not u.get('id'):return None,'Подпись верна, но Telegram не передал user.id'
  return u,'ok'
 except Exception as e:return None,'Ошибка разбора initData: '+type(e).__name__

def verify(raw):
 return verify_detail(raw)[0]

def verify_academy_auth(h):
 try:
  uid=int(h.get('X-Academy-Uid','0') or 0); ts=int(h.get('X-Academy-Ts','0') or 0); got=h.get('X-Academy-Sig','')
  if not uid or not ts or not got:return None
  if abs(int(time.time())-ts)>86400:return None
  payload=f'{uid}:{ts}'
  want=hmac.new(BOT_TOKEN.encode(),payload.encode(),hashlib.sha256).hexdigest() if BOT_TOKEN else ''
  if not want or not hmac.compare_digest(want,got):return None
  return {'id':uid,'first_name':'Ученица','username':'','_auth_reason':'bot_signed_link'}
 except:return None

def verify_academy_query(path):
 try:
  q=urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
  uid=int((q.get('ak_uid') or ['0'])[0]); ts=int((q.get('ak_ts') or ['0'])[0]); got=(q.get('ak_sig') or [''])[0]
  if not uid or not ts or not got or abs(int(time.time())-ts)>86400:return None
  want=hmac.new(BOT_TOKEN.encode(),f'{uid}:{ts}'.encode(),hashlib.sha256).hexdigest() if BOT_TOKEN else ''
  if not want or not hmac.compare_digest(want,got):return None
  return {'id':uid,'first_name':'Ученица','username':'','_auth_reason':'bot_signed_query'}
 except:return None

def user(h):
 raw=h.get('X-Telegram-Init-Data','')
 u,reason=verify_detail(raw)
 if u:
  u['_auth_reason']='telegram_initData'; return u
 signed=verify_academy_auth(h)
 if signed:return signed
 if DEV_USER_ID:return {'id':DEV_USER_ID,'first_name':'Анна','username':'demo','_auth_reason':'DEV_USER_ID'}
 return {'id':0,'first_name':'Анна','username':'preview','_auth_reason':reason}
def display_no(order):return max(0,int(order)-1)
def youtube_id(url):
 if not url:return ''
 m=re.search(r'(?:youtu\.be/|v=|embed/)([A-Za-z0-9_-]{6,})',url); return m.group(1) if m else ''
def shuffled_question(q):
 opts=json.loads(q['options']); random.shuffle(opts)
 fid=str(q.get('photo_file_id') or ''); photo=('/api/runtime-media/'+urllib.parse.quote(Path(fid[8:]).name)) if fid.startswith('runtime:') else (('/api/media/'+urllib.parse.quote(fid)) if fid else ''); return {'id':q['id'],'question_text':q['question_text'],'options':opts,'photo_file_id':fid,'photo_url':photo,'order_num':q.get('order_num')}

def bootstrap(uid,first,auth_reason=""):
 ls=rows('''SELECT l.* FROM lessons l LEFT JOIN academy_lesson_settings s ON s.lesson_id=l.id WHERE COALESCE(s.published,1)=1 ORDER BY l.order_num'''); st=row('SELECT * FROM students WHERE user_id=?',(uid,)) if uid else None; current=int((st or {}).get('current_lesson_order',1))
 attempts=rows('SELECT * FROM attempts WHERE user_id=? ORDER BY finished_at',(uid,)) if uid else []; passed={a['lesson_id'] for a in attempts if a['passed']}
 for l in ls:
  o=int(l['order_num']); l['display_num']=display_no(o); l['state']='done' if l['id'] in passed or o<current else ('current' if o==current else 'locked')
 numbered=[l for l in ls if int(l['order_num'])>1]; completed=sum(1 for l in numbered if l['state']=='done'); total=len(numbered); pct=round(completed/total*100) if total else 0
 wrong=rows('''SELECT a.question_id,a.question_text,a.correct_text,l.id lesson_id,l.title lesson_title,COUNT(*) mistakes FROM answers a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? AND a.is_correct=0 GROUP BY a.question_id,a.question_text,a.correct_text,l.id,l.title ORDER BY mistakes DESC''',(uid,)) if uid else []
 prof=row('SELECT full_name FROM academy_profiles WHERE user_id=?',(uid,)) if uid else None; full=(prof or {}).get('full_name','')
 onboard=row('SELECT completed FROM academy_onboarding WHERE user_id=?',(uid,)) if uid else None
 finals=row('SELECT * FROM academy_final_attempts WHERE user_id=? AND passed=1 ORDER BY finished_at DESC LIMIT 1',(uid,)) if uid else None
 schedule=rows('SELECT * FROM academy_schedule WHERE user_id=? ORDER BY event_date,event_time,order_num,id',(uid,)) if uid else []
 return {'mode':'live','telegram_ready':bool(BOT_TOKEN),'needs_profile':bool(uid and not full),'needs_onboarding':bool(uid and full and not (onboard or {}).get('completed')),'user':{'id':uid,'first_name':first,'full_name':full,'is_admin':uid in ADMIN_IDS,'auth_reason':auth_reason},'progress':{'percent':pct,'completed':completed,'total':total,'current':current,'final_passed':bool(finals),'final_result':finals},'lessons':ls,'mistakes':wrong,'bonus_materials':rows('SELECT * FROM bonus_materials ORDER BY order_num'),'schedule':schedule}

def media_url(fid):
 if str(fid).startswith(('http://','https://')):return str(fid)
 if not BOT_TOKEN:raise RuntimeError('Материал хранится в Telegram. Для него нужно подключить BOT_TOKEN учебного бота в Railway.')
 with urllib.request.urlopen(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={urllib.parse.quote(fid)}',timeout=10) as r:d=json.load(r)
 return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{d['result']['file_path']}"

def telegram_file(fid):
 if str(fid).startswith(('http://','https://')):
  return str(fid),''
 if not BOT_TOKEN:raise RuntimeError('BOT_TOKEN учебного бота не подключен')
 req=urllib.request.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={urllib.parse.quote(str(fid))}',headers={'User-Agent':'ANYA-KAY-Academy/2.6'})
 with urllib.request.urlopen(req,timeout=15) as r:d=json.load(r)
 if not d.get('ok') or not d.get('result',{}).get('file_path'):raise RuntimeError('Telegram не вернул файл. Проверь, что BOT_TOKEN принадлежит тому же учебному боту, куда файл был загружен.')
 fp=d['result']['file_path']
 return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}",Path(fp).name

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
  u=user(self.headers)
  if not u.get('id'):u=verify_academy_query(self.path) or u
  return int(u.get('id',0)),u
 def redirect(self,url,download=None):
  self.send_response(302); self.send_header('Location',url)
  if download:self.send_header('Content-Disposition',f'attachment; filename="{download}"')
  self.end_headers()
 def html_error(self,msg,status=502):
  b=("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{font-family:Arial;background:#f4eee7;color:#241b1d;padding:28px}div{max-width:520px;margin:auto;background:white;padding:22px;border-radius:18px}h2{color:#64142b}</style><div><h2>Материал пока не открывается</h2><p>"+str(msg)+"</p><p>Вернись в Academy. После подключения Telegram-файлов эта кнопка будет работать.</p></div>").encode('utf-8')
  self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def proxy_telegram(self,fid,download=False):
  url,name=telegram_file(fid)
  req=urllib.request.Request(url,headers={'User-Agent':'ANYA-KAY-Academy/2.6'})
  with urllib.request.urlopen(req,timeout=45) as r:
   data=r.read(); ctype=r.headers.get_content_type() or 'application/octet-stream'
   if ctype=='application/octet-stream':
    ext=Path(name).suffix.lower()
    ctype={'.pdf':'application/pdf','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.mp4':'video/mp4','.mov':'video/quicktime','.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}.get(ext,ctype)
  self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','private, max-age=3600')
  if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(name or 'material'))
  else:self.send_header('Content-Disposition','inline')
  self.end_headers(); self.wfile.write(data)
 def do_GET(self):
  p=urllib.parse.urlparse(self.path); uid,u=self.who()
  if p.path=='/health':return self.j({'ok':True,'db':db_ready(),'version':'2.9-safe-fixes'})
  if p.path=='/api/bootstrap':return self.j(bootstrap(uid,u.get('first_name') or 'Ученица',u.get('_auth_reason','')))
  if p.path.startswith('/api/lesson/'):
   lid=int(p.path.rsplit('/',1)[-1]); l=row('SELECT * FROM lessons WHERE id=?',(lid,))
   if not l:return self.j({'error':'not_found'},404)
   l['display_num']=display_no(l['order_num']); l['youtube_id']=youtube_id(l.get('video_url','')); vf=str(l.get('video_file_id') or ''); l['direct_video_url']=('/api/runtime-media/'+urllib.parse.quote(Path(vf[8:]).name)) if vf.startswith('runtime:') else (('/api/media/'+urllib.parse.quote(vf)) if vf else '')
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
   if fid.startswith('runtime:'):
    name=Path(fid[8:]).name; return self.redirect('/api/runtime-media/'+urllib.parse.quote(name)+(('?download=1') if action=='download' else ''))
   if fid.startswith('local:'):
    f=row('SELECT * FROM academy_local_files WHERE key=?',(fid[6:],))
    if not f:return self.j({'error':'Файл не найден'},404)
    target=('previews/'+f['preview_name']) if action=='view' and f.get('preview_name') else ('materials/'+f['stored_name'])
    return self.redirect('/'+target)
   try:return self.proxy_telegram(fid,download=(action=='download'))
   except Exception as e:return self.html_error(str(e))
  if p.path.startswith('/api/media/'):
   try:return self.proxy_telegram(urllib.parse.unquote(p.path.split('/api/media/',1)[1]),download=(urllib.parse.parse_qs(p.query).get('download',['0'])[0]=='1'))
   except Exception as e:return self.html_error(str(e))
  if p.path=='/api/saved':return self.j(rows('SELECT l.* FROM academy_bookmarks b JOIN lessons l ON l.id=b.lesson_id WHERE b.user_id=? ORDER BY b.created_at DESC',(uid,)) if uid else [])
  if p.path=='/api/notes':return self.j(rows('SELECT n.*,l.title,l.order_num FROM academy_notes n JOIN lessons l ON l.id=n.lesson_id WHERE n.user_id=? AND TRIM(n.note)<>"" ORDER BY n.updated_at DESC',(uid,)) if uid else [])
  if p.path=='/api/analytics':
   a=rows('''SELECT l.title,l.order_num,COUNT(a.id) attempts,MAX(CASE WHEN a.passed=1 THEN 1 ELSE 0 END) passed,MAX(CASE WHEN a.total>0 THEN ROUND(a.score*100.0/a.total) ELSE 0 END) best FROM lessons l LEFT JOIN attempts a ON a.lesson_id=l.id AND a.user_id=? GROUP BY l.id ORDER BY l.order_num''',(uid,)) if uid else []
   return self.j(a)
  if p.path=='/api/final/start':
   qs=rows('SELECT * FROM academy_exam_questions ORDER BY order_num'); random.shuffle(qs)
   out=[]
   for q in qs:
    opts=json.loads(q['options']); random.shuffle(opts); out.append({'id':q['id'],'question_text':q['question_text'],'options':opts,'order_num':q['order_num']})
   return self.j({'questions':out,'pass_percent':70})
  if p.path.startswith('/api/runtime-media/'):
   name=Path(urllib.parse.unquote(p.path.split('/api/runtime-media/',1)[1])).name; fp=MEDIA_DIR/name
   if not fp.exists():return self.j({'error':'Файл не найден'},404)
   ctype=mimetypes.guess_type(fp.name)[0] or 'application/octet-stream'; size=fp.stat().st_size; self.send_response(200); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(size)); self.send_header('Cache-Control','private,max-age=3600')
   if urllib.parse.parse_qs(p.query).get('download',['0'])[0]=='1':self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(fp.name))
   else:self.send_header('Content-Disposition','inline')
   self.end_headers()
   with fp.open('rb') as src:
    while True:
     chunk=src.read(1024*1024)
     if not chunk:break
     self.wfile.write(chunk)
   return
  if p.path.startswith('/api/admin/student/'):
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(p.path.rsplit('/',1)[-1]); st=row('SELECT s.*,p.full_name FROM students s LEFT JOIN academy_profiles p ON p.user_id=s.user_id WHERE s.user_id=?',(sid,)) or {'user_id':sid}
   lessons=rows('''SELECT l.id,l.order_num,l.title,COUNT(a.id) attempts,MAX(CASE WHEN a.passed=1 THEN 1 ELSE 0 END) passed,MAX(CASE WHEN a.total>0 THEN ROUND(a.score*100.0/a.total) ELSE 0 END) best FROM lessons l LEFT JOIN attempts a ON a.lesson_id=l.id AND a.user_id=? GROUP BY l.id ORDER BY l.order_num''',(sid,))
   for x in lessons:x['display_num']=display_no(x['order_num'])
   attempts=rows('''SELECT a.*,l.title,l.order_num FROM attempts a JOIN lessons l ON l.id=a.lesson_id WHERE a.user_id=? ORDER BY a.finished_at DESC''',(sid,))
   wrong=rows('''SELECT question_text,chosen_text,correct_text,COUNT(*) mistakes FROM answers WHERE user_id=? AND is_correct=0 GROUP BY question_id,question_text,chosen_text,correct_text ORDER BY mistakes DESC''',(sid,))
   sched=rows('SELECT * FROM academy_schedule WHERE user_id=? ORDER BY event_date,event_time,order_num,id',(sid,))
   fn=rows('SELECT * FROM academy_final_attempts WHERE user_id=? ORDER BY finished_at DESC',(sid,)); an=row('SELECT note FROM academy_admin_notes WHERE user_id=?',(sid,))
   return self.j({'student':st,'lessons':lessons,'attempts':attempts,'mistakes':wrong,'schedule':sched,'final_attempts':fn,'admin_note':(an or {}).get('note','')})
  if p.path=='/api/admin/course':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   ls=rows('''SELECT l.*,COALESCE(s.published,1) published FROM lessons l LEFT JOIN academy_lesson_settings s ON s.lesson_id=l.id ORDER BY l.order_num''')
   for l in ls:l['display_num']=display_no(l['order_num']); l['materials']=rows('SELECT * FROM lesson_materials WHERE lesson_id=? ORDER BY order_num',(l['id'],)); l['question_count']=row('SELECT COUNT(*) n FROM questions WHERE lesson_id=?',(l['id'],))['n']
   return self.j(ls)
  if p.path.startswith('/api/admin/lesson/'):
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   lid=int(p.path.rsplit('/',1)[-1]); l=row('SELECT * FROM lessons WHERE id=?',(lid,));
   if not l:return self.j({'error':'Урок не найден'},404)
   l['materials']=rows('SELECT * FROM lesson_materials WHERE lesson_id=? ORDER BY order_num',(lid,)); l['questions']=rows('SELECT * FROM questions WHERE lesson_id=? ORDER BY order_num',(lid,)); return self.j(l)
  if p.path=='/api/admin/bonus':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   return self.j(rows('SELECT * FROM bonus_materials ORDER BY order_num'))
  if p.path=='/api/admin/overview':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   return self.j({'students':row('SELECT COUNT(*) n FROM students')["n"],'lessons':row('SELECT COUNT(*) n FROM lessons')["n"],'questions':row('SELECT COUNT(*) n FROM questions')["n"],'materials':row('SELECT COUNT(*) n FROM lesson_materials')["n"]+row('SELECT COUNT(*) n FROM bonus_materials')["n"]})
  if p.path=='/api/admin/students':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   return self.j(rows('SELECT s.*,p.full_name profile_name FROM students s LEFT JOIN academy_profiles p ON p.user_id=s.user_id ORDER BY s.last_activity DESC'))
  if p.path.startswith('/api/admin/schedule/'):
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(p.path.rsplit('/',1)[-1]); return self.j(rows('SELECT * FROM academy_schedule WHERE user_id=? ORDER BY event_date,event_time,order_num,id',(sid,)))
  return super().do_GET()
 def do_POST(self):
  p=urllib.parse.urlparse(self.path).path; uid,u=self.who()
  if not uid:return self.j({'error':'Открой приложение внутри Telegram для сохранения данных'},401)
  ensure_tables()
  if p=='/api/admin/upload-file':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   try:name=Path(urllib.parse.unquote(self.headers.get('X-File-Name','file.bin'))).name
   except:name='file.bin'
   length=int(self.headers.get('Content-Length','0') or 0); limit=300*1024*1024
   if length<=0:return self.j({'error':'Пустой файл'},400)
   if length>limit:return self.j({'error':'Файл больше 300 МБ'},413)
   safe=uuid.uuid4().hex+'_'+re.sub(r'[^A-Za-z0-9._-]+','_',name); fp=MEDIA_DIR/safe; left=length
   try:
    with fp.open('wb') as out:
     while left>0:
      chunk=self.rfile.read(min(1024*1024,left))
      if not chunk:break
      out.write(chunk); left-=len(chunk)
    if left!=0:
     try:fp.unlink()
     except:pass
     return self.j({'error':'Загрузка файла оборвалась'},400)
    return self.j({'ok':True,'file_id':'runtime:'+safe,'name':name,'size':length})
   except Exception as e:
    try:fp.unlink()
    except:pass
    return self.j({'error':'Не удалось сохранить файл: '+str(e)},500)
  d=self.body()
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
   given=d.get('answers',{}); qs=rows('SELECT * FROM academy_exam_questions'); score=0; total=len(qs); details=[]
   for q in qs:
    opts=json.loads(q['options']); ct=opts[int(q['correct_index'])]; ch=str(given.get(str(q['id']),'—')); ok=ch==ct; score+=int(ok); details.append({'question_text':q['question_text'],'chosen_text':ch,'correct_text':ct,'is_correct':ok,'order_num':q['order_num']})
   passed=bool(total and score/total>=FINAL_PASS_THRESHOLD); pct=round(score*100/total) if total else 0
   with conn() as c:c.execute('INSERT INTO academy_final_attempts(user_id,score,total,passed) VALUES(?,?,?,?)',(uid,score,total,int(passed)))
   topics=[('Основы: строение, рост и материалы',1,4),('Препараты и клей',5,9),('Постановка и качество работы',10,13),('Объёмы, рядность и моделирование',14,19),('Снятие, коррекция, безопасность и уход',20,24)]; weak=[]
   for title,a,b in topics:
    wrong=sum(1 for x in details if a<=int(x.get('order_num') or 0)<=b and not x['is_correct'])
    if wrong:weak.append({'title':title,'mistakes':wrong})
   weak.sort(key=lambda x:x['mistakes'],reverse=True)
   return self.j({'score':score,'total':total,'percent':pct,'passed':passed,'pass_percent':70,'answers':details,'weak_topics':weak})
  if p=='/api/admin/student/note':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(d['user_id']); note=str(d.get('note',''))
   with conn() as c:c.execute('INSERT INTO academy_admin_notes(user_id,note) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET note=excluded.note,updated_at=CURRENT_TIMESTAMP',(sid,note))
   return self.j({'ok':True})
  if p=='/api/admin/student/reset-test':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(d['user_id']); lid=int(d['lesson_id'])
   with conn() as c:
    aids=[x['id'] for x in c.execute('SELECT id FROM attempts WHERE user_id=? AND lesson_id=?',(sid,lid)).fetchall()]
    if aids:c.execute('DELETE FROM answers WHERE attempt_id IN (%s)'%(','.join('?'*len(aids))),aids)
    c.execute('DELETE FROM attempts WHERE user_id=? AND lesson_id=?',(sid,lid))
   return self.j({'ok':True})
  if p=='/api/admin/student/unlock':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(d['user_id']); order=int(d['order_num'])
   with conn() as c:c.execute('UPDATE students SET current_lesson_order=MAX(current_lesson_order,?) WHERE user_id=?',(order,sid))
   return self.j({'ok':True})
  if p=='/api/admin/lesson/save':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   lid=int(d.get('id') or 0); title=str(d.get('title','')).strip(); desc=str(d.get('description','')); video=str(d.get('video_url','')).strip(); video_file=str(d.get('video_file_id','')).strip(); order=int(d.get('order_num') or 1); published=1 if d.get('published',True) else 0
   if not title:return self.j({'error':'Название обязательно'},400)
   with conn() as c:
    if lid:c.execute('UPDATE lessons SET title=?,description=?,video_url=?,video_file_id=?,order_num=? WHERE id=?',(title,desc,video,video_file,order,lid))
    else:
     cur=c.execute('INSERT INTO lessons(title,description,video_type,video_url,video_file_id,order_num) VALUES(?,?,?,?,?,?)',(title,desc,'url',video,video_file,order)); lid=cur.lastrowid
    c.execute('INSERT INTO academy_lesson_settings(lesson_id,published) VALUES(?,?) ON CONFLICT(lesson_id) DO UPDATE SET published=excluded.published',(lid,published))
   return self.j({'ok':True,'id':lid})
  if p=='/api/admin/lesson/delete':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   lid=int(d['id'])
   with conn() as c:
    c.execute('DELETE FROM lesson_materials WHERE lesson_id=?',(lid,)); c.execute('DELETE FROM questions WHERE lesson_id=?',(lid,)); c.execute('DELETE FROM lessons WHERE id=?',(lid,)); c.execute('DELETE FROM academy_lesson_settings WHERE lesson_id=?',(lid,))
   return self.j({'ok':True})
  if p=='/api/admin/material/save':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   mid=int(d.get('id') or 0); lid=int(d['lesson_id']); caption=str(d.get('caption','Материал')).strip(); ftype=str(d.get('file_type','document')); fid=str(d.get('file_id','')).strip(); order=int(d.get('order_num') or 1)
   with conn() as c:
    if mid:c.execute('UPDATE lesson_materials SET caption=?,file_type=?,file_id=?,order_num=? WHERE id=?',(caption,ftype,fid,order,mid))
    else:c.execute('INSERT INTO lesson_materials(lesson_id,file_type,file_id,caption,order_num) VALUES(?,?,?,?,?)',(lid,ftype,fid,caption,order))
   return self.j({'ok':True})
  if p=='/api/admin/material/delete':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   with conn() as c:c.execute('DELETE FROM lesson_materials WHERE id=?',(int(d['id']),))
   return self.j({'ok':True})
  if p=='/api/admin/upload':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   name=Path(str(d.get('name','file.bin'))).name; raw=str(d.get('data',''))
   if ',' in raw:raw=raw.split(',',1)[1]
   try:data=base64.b64decode(raw,validate=True)
   except:return self.j({'error':'Не удалось прочитать файл'},400)
   if len(data)>120*1024*1024:return self.j({'error':'Файл больше 120 МБ'},413)
   safe=uuid.uuid4().hex+'_'+re.sub(r'[^A-Za-z0-9._-]+','_',name); (MEDIA_DIR/safe).write_bytes(data)
   return self.j({'ok':True,'file_id':'runtime:'+safe,'name':name,'size':len(data)})
  if p=='/api/admin/bonus/save':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   bid=int(d.get('id') or 0); cap=str(d.get('caption','Материал')).strip(); ft=str(d.get('file_type','document')); fid=str(d.get('file_id','')).strip(); order=int(d.get('order_num') or 1)
   with conn() as c:
    if bid:c.execute('UPDATE bonus_materials SET caption=?,file_type=?,file_id=?,order_num=? WHERE id=?',(cap,ft,fid,order,bid))
    else:c.execute('INSERT INTO bonus_materials(file_type,file_id,caption,order_num) VALUES(?,?,?,?)',(ft,fid,cap,order))
   return self.j({'ok':True})
  if p=='/api/admin/bonus/delete':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   with conn() as c:c.execute('DELETE FROM bonus_materials WHERE id=?',(int(d['id']),))
   return self.j({'ok':True})
  if p=='/api/admin/question/save':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   qid=int(d.get('id') or 0); lid=int(d['lesson_id']); text=str(d.get('question_text','')).strip(); opts=d.get('options') or []; ci=int(d.get('correct_index',0)); expl=str(d.get('explanation','')); photo=str(d.get('photo_file_id','')); order=int(d.get('order_num') or 1)
   if not text or len(opts)<2:return self.j({'error':'Заполни вопрос и варианты'},400)
   with conn() as c:
    if qid:c.execute('UPDATE questions SET question_text=?,options=?,correct_index=?,explanation=?,photo_file_id=?,order_num=? WHERE id=?',(text,json.dumps(opts,ensure_ascii=False),ci,expl,photo,order,qid))
    else:c.execute('INSERT INTO questions(lesson_id,question_text,options,correct_index,explanation,photo_file_id,order_num) VALUES(?,?,?,?,?,?,?)',(lid,text,json.dumps(opts,ensure_ascii=False),ci,expl,photo,order))
   return self.j({'ok':True})
  if p=='/api/admin/question/delete':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   with conn() as c:c.execute('DELETE FROM questions WHERE id=?',(int(d['id']),))
   return self.j({'ok':True})
  if p=='/api/admin/schedule/save':
   if uid not in ADMIN_IDS:return self.j({'error':'Нет доступа'},403)
   sid=int(d['user_id']); eid=int(d.get('id') or 0); vals=(str(d['event_date']),str(d.get('event_time','')),str(d['title']).strip(),str(d.get('notes','')),int(d.get('order_num',1)))
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
 ensure_tables(); print(f'ANYA KAY Academy v2.9 SAFE FIXES on :{PORT} | DB={DB_PATH}'); ThreadingHTTPServer(('0.0.0.0',PORT),H).serve_forever()
