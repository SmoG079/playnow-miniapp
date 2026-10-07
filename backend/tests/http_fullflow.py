"""Destructive fixture exercise: run ONLY against an isolated scratch deployment."""
import datetime,json,httpx,sys,base64
import os
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
url=make_url(os.environ['DATABASE_URL'])
assert url.database.startswith('playnow_e2e_') or url.database=='test_db', 'Isolated database required'
c=httpx.Client(base_url='http://127.0.0.1:18080/api/v1',timeout=20)
checks=[]
def call(method,path,token=None,expected=200,**kw):
    r=c.request(method,path,headers={'Authorization':'Bearer '+token} if token else {},**kw)
    ok=r.status_code==expected
    checks.append({'method':method,'path':path,'expected':expected,'actual':r.status_code,'passed':ok})
    if not ok:
        print(json.dumps(checks,indent=2));raise AssertionError(f'{method} {path}: {r.status_code} {r.text[:700]}')
    return r.json() if r.content and 'application/json' in r.headers.get('content-type','') else r.content
owner_login=call('POST','/auth/login',json={'code':'dev_e2e_owner'})
owner=owner_login['access_token']
admin=call('POST','/auth/login',json={'code':'dev_e2e_admin'})['access_token']
engine=create_engine(url.set(drivername='mysql+pymysql'))
with engine.begin() as conn:
    conn.execute(text("UPDATE users SET role='platform_admin' WHERE openid='dev_e2e_admin'"))
engine.dispose()
member=call('POST','/auth/login',json={'code':'dev_e2e_member'})['access_token']
other=call('POST','/auth/login',json={'code':'dev_e2e_other'})['access_token']
assert call('POST','/auth/refresh',json={'refresh_token':owner_login['refresh_token']})['access_token']
call('GET','/users/me',expected=401)
call('PUT','/users/me',owner,json={'nickname':'E2E owner','ntrp_level':3.5})
assert str(call('GET','/users/me',owner)['ntrp_level'])=='3.5'
member_id=call('GET','/users/me',member)['id']
call('PUT','/users/me',member,expected=422,json={'ntrp_level':8})
club=call('POST','/clubs',owner,json={'name':'E2E isolated club','contact_phone':'13800000000','sport_types':['tennis'],'opening_time':'08:00','closing_time':'22:00'})['id']
assert club in call('GET','/users/me',owner)['managed_club_ids']
call('GET','/clubs');call('GET',f'/clubs/{club}')
call('PUT',f'/clubs/{club}',owner,json={'description':'scratch verification'})
call('PUT',f'/clubs/{club}',other,expected=403,json={'name':'unauthorized'})
venue=call('POST',f'/venues/with-club/{club}',owner,json={'name':'E2E court','price_per_hour':100})['id']
call('GET',f'/venues/{venue}');call('GET',f'/clubs/{club}/venues')
call('PUT',f'/venues/{venue}/with-club/{club}',owner,json={'price_per_hour':120})
call('DELETE',f'/venues/{venue}/with-club/{club}',other,expected=403)
date=(datetime.date.today()+datetime.timedelta(days=7)).isoformat()
slotspec={'date_from':date,'date_to':date,'start_time':'08:00','end_time':'12:00','interval_minutes':60}
assert call('POST',f'/venues/{venue}/slots/batch',owner,json=slotspec)['created']==4
assert call('POST',f'/venues/{venue}/slots/batch',owner,json=slotspec)['skipped']==4
slots=call('GET',f'/venues/{venue}/slots',params={'date':date})
assert float(slots[0]['slots'][0]['price'])==120
assert call('GET',f'/venues/{venue}/slots',params={'date_from':date,'date_to':date})==slots

if isinstance(slots,dict): groups=slots.get('items',slots.get('dates',slots.get('slots',[])))
else: groups=slots
if groups and 'slots' in groups[0]: slots=groups[0]['slots']
else: slots=groups
ids=[s['id'] for s in slots]
call('PUT',f'/venues/{venue}/with-club/{club}',owner,json={'price_rules':[{'type':'time_range','start_time':'08:00','end_time':'10:00','price':180}]})
grid=call('GET',f'/clubs/{club}/venue-slots',params={'date':date})
quoted=sum(float(cell['price']) for row in grid['rows'] for cell in row['cells'] if cell['slot_id'] in ids[:2])
assert quoted==360
assert float(call('GET',f'/venues/{venue}/slots',params={'date':date})[0]['slots'][0]['price'])==180
call('PATCH',f'/venues/{venue}/slots/{ids[0]}/status',owner,json={'status':'maintenance'})
call('POST','/bookings',member,expected=409,json={'slot_id':ids[0]})
call('PATCH',f'/venues/{venue}/slots/{ids[0]}/status',owner,json={'status':'available'})
call('POST','/bookings',member,expected=422,json={})
booking=call('POST','/bookings',member,json={'slot_ids':ids[:2]})
assert float(booking['amount'])==quoted, (booking['amount'],quoted)
bid=booking['id']
call('POST','/bookings',other,expected=409,json={'slot_id':ids[0]})
call('GET',f'/bookings/{bid}',member)
call('GET',f'/bookings/{bid}',other,expected=403)
call('GET','/users/me/bookings',member)
call('GET',f'/bookings/club/{club}',owner)
call('GET','/bookings/config')
call('GET',f'/bookings/{bid}/refund-records',member)
call('GET','/bookings/settlements',owner,expected=403)
assert call('GET','/bookings/settlements',admin)['total']==0
call('GET','/bookings/settlements',member,expected=403)
call('POST',f'/bookings/{bid}/cancel',member,json={'reason':'isolated test'})
assert call('GET',f'/bookings/{bid}',member)['status']=='cancelled'
post=call('POST','/posts',owner,json={'title':'E2E approval post','price':0,'players_needed':2,'approval_required':True})['id']
call('GET','/posts');call('GET',f'/posts/{post}')
call('PUT',f'/posts/{post}',owner,json={'notes':'updated'})
call('PUT',f'/posts/{post}',other,expected=403,json={'title':'unauthorized'})
call('POST',f'/posts/{post}/register',member,json={'message':'join'})
call('POST',f'/posts/{post}/register',member,expected=409,json={})
call('PUT',f'/posts/{post}/registrations/{member_id}',owner,json={'status':'approved'})
assert call('GET',f'/posts/{post}')['registrations'][0]['status']=='approved'
call('GET','/users/me/posts',owner)
registrations=call('GET','/users/me/registrations',member)
assert registrations['total']==1 and registrations['items'][0]['ref_id']==post
assert registrations['items'][0]['status']=='approved'
assert call('GET','/users/me/registrations',other)['total']==0
comment=call('POST',f'/posts/{post}/comments',member,json={'content':'hello'})['id']
reply=call('POST',f'/posts/{post}/comments',owner,json={'content':'reply','parent_id':comment})
assert call('GET',f'/posts/{post}/comments')['items'][0]['reply_count']==1
call('DELETE',f'/posts/{post}/comments/{comment}',other,expected=403)
call('DELETE',f'/posts/{post}/comments/{comment}',member)
assert call('GET','/users/me/notifications/unread-count',owner)['count']>0
notifications=call('GET','/users/me/notifications',owner)['items']
nid=notifications[0]['id']
call('GET',f'/users/me/notifications/{nid}',owner)
call('GET',f'/users/me/notifications/{nid}',other,expected=404)
call('PUT',f'/users/me/notifications/{nid}/read',owner)
call('PUT','/users/me/notifications/read-all',owner)
assert call('GET','/users/me/notifications/unread-count',owner)['count']==0
call('DELETE',f'/posts/{post}/register',member)
assert call('GET','/users/me/registrations',member)['total']==0
call('DELETE',f'/posts/{post}',other,expected=403)
call('DELETE',f'/posts/{post}',owner)
call('GET',f'/posts/{post}',expected=404)
start=date+'T14:00:00';end=date+'T16:00:00'
tournament=call('POST','/tournaments',owner,json={'club_id':club,'title':'E2E free tournament','start_time':start,'end_time':end,'entry_fee':0,'max_participants':4})['id']
call('GET','/tournaments');call('GET',f'/tournaments/{tournament}')
call('PUT',f'/tournaments/{tournament}',owner,json={'description':'updated'})
assert call('POST',f'/tournaments/{tournament}/register',member)['order'] is None
assert call('GET',f'/tournaments/{tournament}')['current_participants']==1
registrations=call('GET','/users/me/registrations',member)
assert registrations['total']==1 and registrations['items'][0]['ref_type']=='tournament'
assert registrations['items'][0]['status']=='confirmed'
call('GET',f'/clubs/{club}/stats',owner)
image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jMZkAAAAASUVORK5CYII=')
upload=call('POST','/upload',owner,files={'file':('e2e.png',image,'image/png')})
assert c.get(upload['url']).content==image
call('POST','/upload',owner,expected=400,files={'file':('invalid.txt',b'test','text/plain')})
created=call('POST',f'/venues/with-club/{club}',owner,json={'name':'empty court','price_per_hour':80,'price_rules':[{'type':'time_range','start_time':'18:00','end_time':'22:00','price':100}]})
assert created['price_rules'][0]['price']==100
unused=created['id']
call('DELETE',f'/venues/{unused}/with-club/{club}',owner)
report={'checks':checks,'passed':len(checks),'payment_refund':'deferred','real_wechat_login_phone_geocoding':'not exercised'}
open(os.environ.get('FULLFLOW_REPORT','/workspace/fullflow-result.json'),'w').write(json.dumps(report,indent=2))
print('FULLFLOW_PASSED',len(checks))
