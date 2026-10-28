#!/usr/bin/env python3
"""Aura Salon & Studio — standard-library HTTP API + persistent SQLite database."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from zoneinfo import ZoneInfo
import sqlite3, json, os, re, secrets, hashlib, hmac, datetime, threading, urllib.request, urllib.error

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('DATABASE_PATH', ROOT / 'salon.db'))
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', '8000'))
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'AuraDemo2026!')
ADMIN_TOKEN = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
DB_LOCK = threading.RLock()
SERVICES = [('Haircut',200,30),('Beard Trim',100,15),('Hair Spa',800,45),('Facial',500,40),('Bridal Makeup',5000,120)]
OPEN_MIN = 10*60
CLOSE_MIN = 20*60
SLOT_STEP = 15


def conn():
    c = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    return c

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DB_LOCK, conn() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, price INTEGER NOT NULL CHECK(price>=0), duration INTEGER NOT NULL CHECK(duration>0));
        CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL, phone TEXT NOT NULL, service_id INTEGER NOT NULL REFERENCES services(id), date TEXT NOT NULL, time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Confirmed','Done','Cancelled')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_bookings_date_status ON bookings(date,status,time);
        CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_number TEXT NOT NULL UNIQUE, customer_name TEXT NOT NULL, phone TEXT NOT NULL, booking_id INTEGER REFERENCES bookings(id), subtotal INTEGER NOT NULL, total INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS invoice_items(id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE, service_id INTEGER REFERENCES services(id), service_name TEXT NOT NULL, unit_price INTEGER NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), line_total INTEGER NOT NULL);
        ''')
        for name, price, duration in SERVICES:
            c.execute('INSERT OR IGNORE INTO services(name,price,duration) VALUES(?,?,?)',(name,price,duration))
        count = c.execute('SELECT COUNT(*) n FROM bookings').fetchone()['n']
        if count == 0:
            today = datetime.date.today()
            now = datetime.datetime.now()
            # One past Done sample, plus two future samples on separate dates.
            samples = [
                ('Aarav Mehta','9876543210','Haircut',(today-datetime.timedelta(days=1)).isoformat(),'11:00','Done'),
                ('Riya Sharma','9123456780','Facial',(today+datetime.timedelta(days=1)).isoformat(),'12:00','Pending'),
                ('Kabir Iyer','9988776655','Hair Spa',(today+datetime.timedelta(days=1)).isoformat(),'14:00','Confirmed'),
            ]
            for name, phone, service, date, time, status in samples:
                sid=c.execute('SELECT id FROM services WHERE name=?',(service,)).fetchone()['id']
                ts=now.isoformat(timespec='seconds')
                c.execute('INSERT INTO bookings(customer_name,phone,service_id,date,time,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(name,phone,sid,date,time,status,ts,ts))

def as_dict(row): return dict(row) if row is not None else None
def service_by_id(c, sid): return c.execute('SELECT * FROM services WHERE id=?',(sid,)).fetchone()
def booking_query(c, where='', args=()):
    sql='''SELECT b.*,s.name service_name,s.price service_price,s.duration service_duration FROM bookings b JOIN services s ON s.id=b.service_id'''
    if where: sql+=' WHERE '+where
    sql+=' ORDER BY b.date DESC,b.time ASC'
    return [dict(x) for x in c.execute(sql,args).fetchall()]
def parse_date_time(date, time):
    try: d=datetime.date.fromisoformat(date); t=datetime.time.fromisoformat(time)
    except (ValueError, TypeError): raise ValueError('Choose a valid appointment date and time.')
    return datetime.datetime.combine(d,t)
def local_now(): return datetime.datetime.now(ZoneInfo('Asia/Kolkata')).replace(tzinfo=None)
def ensure_future(date,time):
    dt=parse_date_time(date,time)
    if dt <= local_now(): raise ValueError('Please choose a future appointment time.')
    if dt.date().isoformat()!=date: raise ValueError('Invalid appointment date.')
    if dt.hour*60+dt.minute < OPEN_MIN or dt.hour*60+dt.minute >= CLOSE_MIN or dt.minute%SLOT_STEP:
        raise ValueError('Choose a slot between 10:00 AM and 7:45 PM in 15-minute increments.')
    return dt

def is_conflict(c, date, start_time, duration, exclude_id=None):
    start=parse_date_time(date,start_time)
    end=start+datetime.timedelta(minutes=duration)
    rows=c.execute('''SELECT b.id,b.date,b.time,s.duration FROM bookings b JOIN services s ON s.id=b.service_id WHERE b.date=? AND b.status IN ('Pending','Confirmed')''',(date,)).fetchall()
    for row in rows:
        if exclude_id is not None and row['id']==exclude_id: continue
        other=parse_date_time(row['date'],row['time']); other_end=other+datetime.timedelta(minutes=row['duration'])
        if start < other_end and other < end: return row['id']
    return None

def available_slots(date, sid, exclude_id=None):
    try: d=datetime.date.fromisoformat(date)
    except Exception: raise ValueError('Choose a valid date.')
    with DB_LOCK, conn() as c:
        s=service_by_id(c,sid)
        if not s: raise ValueError('Select a valid service.')
        slots=[]
        for mins in range(OPEN_MIN,CLOSE_MIN-SLOT_STEP+1,SLOT_STEP):
            if mins+s['duration']>CLOSE_MIN: continue
            hh,mm=divmod(mins,60); tm=f'{hh:02d}:{mm:02d}'
            if d==local_now().date() and parse_date_time(date,tm)<=local_now(): continue
            if not is_conflict(c,date,tm,s['duration'],exclude_id): slots.append(tm)
        return slots

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT/'static'),**kwargs)
    def log_message(self, fmt,*args): print('[http]',fmt%args)
    def send_json(self, code, data):
        raw=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.send_header('Access-Control-Allow-Origin', os.getenv('FRONTEND_ORIGIN','*')); self.send_header('Access-Control-Allow-Headers','Content-Type, X-Admin-Password'); self.send_header('Access-Control-Allow-Methods','GET,POST,PATCH,OPTIONS'); self.end_headers(); self.wfile.write(raw)
    def read_body(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>1_000_000: raise ValueError('Request is too large.')
            return json.loads(self.rfile.read(n) or b'{}')
        except (json.JSONDecodeError,ValueError) as e: raise ValueError('Request body must be valid JSON.') from e
    def admin(self):
        supplied=self.headers.get('X-Admin-Password','')
        return hmac.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(), ADMIN_TOKEN)
    def do_OPTIONS(self): self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Content-Type, X-Admin-Password'); self.send_header('Access-Control-Allow-Methods','GET,POST,PATCH,OPTIONS'); self.end_headers()
    def do_GET(self):
        u=urlparse(self.path); path=u.path; q=parse_qs(u.query)
        try:
            if path=='/api/health': return self.send_json(200,{'ok':True,'database':'sqlite','salon':'Aura Salon & Studio'})
            if path=='/api/services':
                with conn() as c: return self.send_json(200,[dict(x) for x in c.execute('SELECT id,name,price,duration FROM services ORDER BY id').fetchall()])
            if path=='/api/availability':
                date=q.get('date',[''])[0]; sid=int(q.get('serviceId',['0'])[0]); exclude=int(q.get('excludeId',['0'])[0]) or None
                try: slots=available_slots(date,sid,exclude)
                except ValueError as e: return self.send_json(400,{'error':str(e)})
                return self.send_json(200,{'date':date,'serviceId':sid,'slots':slots,'openingHours':'10:00–20:00','slotIntervalMinutes':15})
            if path=='/api/bookings':
                if not self.admin(): return self.send_json(401,{'error':'Admin login required.'})
                with conn() as c:
                    where=[]; args=[]
                    if q.get('date'): where.append('b.date=?'); args.append(q['date'][0])
                    if q.get('status') and q['status'][0]!='All': where.append('b.status=?'); args.append(q['status'][0])
                    if q.get('search'):
                        where.append('(LOWER(b.customer_name) LIKE ? OR b.phone LIKE ?)'); term='%'+q['search'][0].lower()+'%'; args.extend([term,term])
                    return self.send_json(200,booking_query(c,' AND '.join(where),args))
            if path.startswith('/api/bookings/') and path.endswith('/public'):
                try: bid=int(path.split('/')[-2])
                except: return self.send_json(404,{'error':'Booking not found.'})
                phone=q.get('phone',[''])[0]
                with conn() as c:
                    b=c.execute('SELECT b.id,b.customer_name,b.phone,b.date,b.time,b.status,s.name service_name,s.price service_price,s.duration service_duration FROM bookings b JOIN services s ON s.id=b.service_id WHERE b.id=? AND b.phone=?',(bid,phone)).fetchone()
                    if not b:return self.send_json(404,{'error':'Booking not found. Check the reference and phone number.'})
                    return self.send_json(200,dict(b))
            if path.startswith('/api/invoices/'):
                if not self.admin(): return self.send_json(401,{'error':'Admin login required.'})
                try: iid=int(path.split('/')[-1])
                except: return self.send_json(404,{'error':'Invoice not found.'})
                with conn() as c:
                    inv=c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone()
                    if not inv:return self.send_json(404,{'error':'Invoice not found.'})
                    out=dict(inv);out['items']=[dict(x) for x in c.execute('SELECT service_name,unit_price,quantity,line_total FROM invoice_items WHERE invoice_id=?',(iid,)).fetchall()]
                    return self.send_json(200,out)
            return super().do_GET()
        except Exception as e: return self.send_json(500,{'error':'Unexpected server error.','detail':str(e) if os.getenv('DEBUG')=='1' else None})
    def do_POST(self):
        path=urlparse(self.path).path
        try: data=self.read_body()
        except ValueError as e:return self.send_json(400,{'error':str(e)})
        try:
            if path=='/api/admin/login':
                if hmac.compare_digest(str(data.get('password','')),ADMIN_PASSWORD): return self.send_json(200,{'ok':True,'message':'Admin login successful.'})
                return self.send_json(401,{'error':'Incorrect admin password.'})
            if path=='/api/bookings':
                name=str(data.get('customer_name','')).strip(); phone=str(data.get('phone','')).strip(); date=str(data.get('date','')); time=str(data.get('time','')); sid=data.get('service_id')
                if not name or len(name)>100:return self.send_json(400,{'error':'Enter a customer name (maximum 100 characters).'})
                if not re.fullmatch(r'\d{10}',phone):return self.send_json(400,{'error':'Phone number must contain exactly 10 digits.'})
                if not date or not time or sid in (None,''):return self.send_json(400,{'error':'Complete all booking fields.'})
                try: sid=int(sid); ensure_future(date,time)
                except (ValueError,TypeError) as e:return self.send_json(400,{'error':str(e) or 'Invalid service.'})
                with DB_LOCK, conn() as c:
                    c.execute('BEGIN IMMEDIATE')
                    s=service_by_id(c,sid)
                    if not s:c.rollback();return self.send_json(400,{'error':'Selected service does not exist.'})
                    if is_conflict(c,date,time,s['duration']):c.rollback();return self.send_json(409,{'error':'That time is no longer available. Please choose another slot.'})
                    ts=datetime.datetime.now().isoformat(timespec='seconds')
                    cur=c.execute("INSERT INTO bookings(customer_name,phone,service_id,date,time,status,created_at,updated_at) VALUES(?,?,?,?,?,'Pending',?,?)",(name,phone,sid,date,time,ts,ts)); bid=cur.lastrowid
                    b=c.execute('SELECT b.*,s.name service_name,s.price service_price,s.duration service_duration FROM bookings b JOIN services s ON s.id=b.service_id WHERE b.id=?',(bid,)).fetchone(); c.commit()
                    return self.send_json(201,dict(b))
            if path.startswith('/api/bookings/') and path.endswith('/reschedule'):
                try: bid=int(path.split('/')[-2])
                except: return self.send_json(404,{'error':'Booking not found.'})
                phone=str(data.get('phone','')).strip(); date=str(data.get('date','')); time=str(data.get('time',''))
                try: ensure_future(date,time)
                except ValueError as e:return self.send_json(400,{'error':str(e)})
                with DB_LOCK, conn() as c:
                    c.execute('BEGIN IMMEDIATE'); b=c.execute('SELECT * FROM bookings WHERE id=? AND phone=?',(bid,phone)).fetchone()
                    if not b or b['status'] in ('Cancelled','Done'):c.rollback();return self.send_json(404,{'error':'Booking not found or cannot be changed.'})
                    s=service_by_id(c,b['service_id'])
                    if is_conflict(c,date,time,s['duration'],bid):c.rollback();return self.send_json(409,{'error':'That time is not available.'})
                    c.execute('UPDATE bookings SET date=?,time=?,updated_at=? WHERE id=?',(date,time,datetime.datetime.now().isoformat(timespec='seconds'),bid)); c.commit()
                    return self.send_json(200,{'ok':True,'message':'Booking rescheduled.','booking_id':bid,'date':date,'time':time})
            if path.startswith('/api/bookings/') and path.endswith('/cancel'):
                try: bid=int(path.split('/')[-2])
                except: return self.send_json(404,{'error':'Booking not found.'})
                phone=re.sub(r'\D','',str(data.get('phone','')))
                with DB_LOCK, conn() as c:
                    cur=c.execute("UPDATE bookings SET status='Cancelled',updated_at=? WHERE id=? AND phone=? AND status IN ('Pending','Confirmed')",(datetime.datetime.now().isoformat(timespec='seconds'),bid,phone))
                    if cur.rowcount==0:return self.send_json(404,{'error':'Booking not found or cannot be cancelled.'})
                    return self.send_json(200,{'ok':True,'message':'Booking cancelled.'})
            if path=='/api/invoices':
                if not self.admin():return self.send_json(401,{'error':'Admin login required.'})
                customer=str(data.get('customer_name','')).strip(); phone=str(data.get('phone','')).strip(); items=data.get('items',[]); booking_id=data.get('booking_id')
                if not customer or not re.fullmatch(r'\d{10}',phone):return self.send_json(400,{'error':'Enter customer name and a valid 10-digit phone number.'})
                if not isinstance(items,list) or not items:return self.send_json(400,{'error':'Add at least one service.'})
                with DB_LOCK, conn() as c:
                    c.execute('BEGIN IMMEDIATE'); prepared=[]; total=0
                    for item in items:
                        try: sid=int(item.get('service_id')); qty=int(item.get('quantity',1))
                        except: c.rollback();return self.send_json(400,{'error':'Invalid invoice item.'})
                        s=service_by_id(c,sid)
                        if not s or qty<1 or qty>50:c.rollback();return self.send_json(400,{'error':'Invalid service or quantity.'})
                        line=s['price']*qty;total+=line;prepared.append((sid,s['name'],s['price'],qty,line))
                    number='AURA-'+datetime.datetime.now().strftime('%Y%m%d')+'-'+secrets.token_hex(3).upper(); ts=datetime.datetime.now().isoformat(timespec='seconds')
                    cur=c.execute('INSERT INTO invoices(invoice_number,customer_name,phone,booking_id,subtotal,total,created_at) VALUES(?,?,?,?,?,?,?)',(number,customer,phone,booking_id,total,total,ts)); iid=cur.lastrowid
                    for row in prepared:c.execute('INSERT INTO invoice_items(invoice_id,service_id,service_name,unit_price,quantity,line_total) VALUES(?,?,?,?,?,?)',(iid,*row))
                    c.commit();return self.send_json(201,{'id':iid,'invoice_number':number,'customer_name':customer,'phone':phone,'subtotal':total,'total':total,'created_at':ts,'items':[{'service_name':x[1],'unit_price':x[2],'quantity':x[3],'line_total':x[4]} for x in prepared]})
            if path=='/api/chat': return self.chat(data)
            return self.send_json(404,{'error':'Endpoint not found.'})
        except Exception as e:
            return self.send_json(500,{'error':'Unexpected server error.','detail':str(e) if os.getenv('DEBUG')=='1' else None})
    def do_PATCH(self):
        path=urlparse(self.path).path
        if not path.startswith('/api/bookings/'):return self.send_json(404,{'error':'Endpoint not found.'})
        if not self.admin():return self.send_json(401,{'error':'Admin login required.'})
        try: data=self.read_body();bid=int(path.split('/')[-1])
        except Exception:return self.send_json(400,{'error':'Invalid request.'})
        status=data.get('status'); allowed={'Pending':{'Confirmed','Cancelled'},'Confirmed':{'Done','Cancelled'},'Done':set(),'Cancelled':set()}
        if status not in allowed:return self.send_json(400,{'error':'Invalid status.'})
        with DB_LOCK, conn() as c:
            b=c.execute('SELECT status FROM bookings WHERE id=?',(bid,)).fetchone()
            if not b:return self.send_json(404,{'error':'Booking not found.'})
            if status not in allowed[b['status']]:return self.send_json(409,{'error':f"Cannot change {b['status']} to {status}."})
            c.execute('UPDATE bookings SET status=?,updated_at=? WHERE id=?',(status,datetime.datetime.now().isoformat(timespec='seconds'),bid))
            return self.send_json(200,{'ok':True,'id':bid,'status':status})
    def chat(self,data):
        msg=str(data.get('message','')).strip()
        if not msg:return self.send_json(400,{'error':'Enter a message.'})
        if len(msg)>1200:return self.send_json(400,{'error':'Message is too long.'})
        with conn() as c: services=[dict(x) for x in c.execute('SELECT name,price,duration FROM services ORDER BY id').fetchall()]
        # Optional server-side OpenAI-compatible provider. Safe grounded fallback works without a key.
        api_key=os.getenv('LLM_API_KEY'); provider=os.getenv('LLM_PROVIDER','openai').lower()
        if api_key:
            try:
                prompt=(ROOT/'prompts'/'salon-chatbot-system-prompt.txt').read_text(encoding='utf-8')
                system=prompt+'\n\nLIVE SERVICE CATALOG (trusted backend data): '+json.dumps(services,ensure_ascii=False)+'\nOpening hours: 10:00 AM to 8:00 PM IST. For live availability, tell the user to select a date and service in the booking form; never infer availability.'
                if provider=='gemini':
                    url='https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key='+api_key
                    payload={'system_instruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':msg}]}],'generationConfig':{'temperature':0.2,'maxOutputTokens':250}}
                    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
                    with urllib.request.urlopen(req,timeout=12) as res: out=json.loads(res.read())
                    answer=out['candidates'][0]['content']['parts'][0]['text']
                else:
                    url=os.getenv('LLM_BASE_URL','https://api.openai.com/v1/chat/completions')
                    payload={'model':os.getenv('LLM_MODEL','gpt-4o-mini'),'temperature':0.2,'max_tokens':250,'messages':[{'role':'system','content':system},{'role':'user','content':msg}]}
                    req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+api_key},method='POST')
                    with urllib.request.urlopen(req,timeout=12) as res: out=json.loads(res.read())
                    answer=out['choices'][0]['message']['content']
                return self.send_json(200,{'answer':answer,'mode':'llm'})
            except Exception as e: print('[chat] LLM provider failed:',type(e).__name__)
        answer=grounded_reply(msg,services)
        return self.send_json(200,{'answer':answer,'mode':'grounded-fallback'})

def grounded_reply(message, services):
    m=message.lower(); norm=re.sub(r'[^a-z0-9\s]', ' ', m); norm=' '.join(norm.split())
    if any(x in norm for x in ['ignore previous','ignore your rules','reveal prompt','system prompt','api key','other customer','another customer','customer phone','home delivery','home visit','come to my home','ghar pe','ghar par','delivery']):
        if any(x in norm for x in ['home delivery','home visit','come to my home','ghar pe','ghar par','delivery']): return 'I can help with in-salon services and appointments. I cannot confirm home visits or delivery. You can view our services and book a salon appointment here.'
        return 'I can help with salon services, prices, opening hours, and booking guidance. I can’t share private customer information or internal system instructions.'
    found=[]
    for s in services:
        aliases=[s['name'].lower()]
        if s['name']=='Haircut': aliases+=['hair cut','baal katna','hair cut ka']
        if s['name']=='Beard Trim': aliases+=['beard','daadhi','dadhi','trim']
        if s['name']=='Hair Spa': aliases+=['hairspa','hair spa','baal spa']
        if s['name']=='Facial': aliases+=['face cleanup','chehre ka','facial ka']
        if s['name']=='Bridal Makeup': aliases+=['bridal','makeup','dulhan']
        if any(a in norm for a in aliases): found.append(s)
    asks_price=any(x in norm for x in ['price','cost','kitne','kitna','rate','rupee','rupees','paisa','daam','kiti','kimat','कितने','कितना','किंमत'])
    asks_time=any(x in norm for x in ['time','timing','open','close','hours','kab khulta','kab band','timings','वेळ','kiti vajta'])
    asks_available=any(x in norm for x in ['available','slot','free hai','book','booking','4 baje','aaj','tomorrow','kal','appointment'])
    if found:
        lines=[f"{s['name']}: ₹{s['price']:,} · {s['duration']} minutes" for s in found]
        if asks_available:return 'To check live slot availability, choose the service and date in the booking form. The app will show only available times. Our salon hours are 10:00 AM–8:00 PM IST.\n\n'+ '\n'.join(lines)
        return '\n'.join(lines)+('\n\nWe are open daily from 10:00 AM to 8:00 PM IST.' if asks_time else '')
    if asks_time:return 'Aura Salon & Studio is open daily from 10:00 AM to 8:00 PM IST. Select a service and date in the booking form to see available appointment times.'
    if asks_available:return 'I can help you check a slot. Please select your service and preferred date in the booking form; it checks current availability before you book.'
    return 'I can help with our services, prices, opening hours, and booking steps. Try asking “Haircut kitne ka hai?” or “Mala facial chi price sang.”'

if __name__=='__main__':
    init_db()
    print(f'Aura Salon server running at http://{HOST}:{PORT} | DB: {DB_PATH}')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
