#!/usr/bin/env python3
"""Create signed negative fixtures from a freshly issued acceptance Work Order.
Run only as root on the disposable acceptance VPS. It never changes production DB.
"""
import base64,copy,json,os,pathlib,sys,uuid
from datetime import datetime,timedelta,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
if os.geteuid()!=0:raise SystemExit('root required')
src=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(mode=0o700,parents=True,exist_ok=True)
key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(os.environ['WO_SIGNING_KEY_B64']))
base=json.loads(src.read_text())
def write(name,edit):
 m=copy.deepcopy(base);edit(m);m.pop('signature',None);raw=json.dumps(m,sort_keys=True,separators=(',',':')).encode();m['signature']='ed25519:'+base64.b64encode(key.sign(raw)).decode();(out/f'{name}.json').write_text(json.dumps(m));os.chmod(out/f'{name}.json',0o600)
now=datetime.now(timezone.utc)
write('expired',lambda m:m.update(expires_at=(now-timedelta(seconds=1)).isoformat()))
write('future',lambda m:m.update(not_before=(now+timedelta(hours=1)).isoformat()))
write('other-principal',lambda m:m['subject'].update(principal_id=str(uuid.uuid4()),unix_user=os.environ.get('ACCEPTANCE_OTHER_USER','definitely-not-current-user')))
print(out)
