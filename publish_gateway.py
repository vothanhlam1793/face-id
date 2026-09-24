"""Run on SVR12 via stdin. Uses its existing Cloudflare credential in place."""
import json
import pathlib
import subprocess
import urllib.request

domain = 'novaface.nvlit.asia'
credential = pathlib.Path('/root/cloudflare.ini').read_text()
token = next(line.split('=',1)[1].strip() for line in credential.splitlines() if line.strip().startswith('dns_cloudflare_api_token'))
def cf(path, body=None, method=None):
    req = urllib.request.Request('https://api.cloudflare.com/client/v4/'+path, data=json.dumps(body).encode() if body else None, headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}, method=method)
    response = json.load(urllib.request.urlopen(req, timeout=30))
    if not response['success']:
        raise RuntimeError('Cloudflare request unsuccessful')
    return response['result']

zones = cf('zones?name=nvlit.asia')
if not zones:
    raise RuntimeError('Zone permission unavailable')
zone = zones[0]['id']
records = cf(f'zones/{zone}/dns_records?name={domain}')
print('Existing exact DNS records:', len(records))
vhost = pathlib.Path('/etc/nginx/sites-available/'+domain+'.conf')
if vhost.exists():
    raise RuntimeError('Vhost already exists; inspect before replacing')
conf = '''server {
    listen 80;
    server_name novaface.nvlit.asia;
    client_max_body_size 11m;
    location / {
        proxy_pass http://10.7.0.21:8020;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
'''
vhost.write_text(conf)
pathlib.Path('/etc/nginx/sites-enabled/'+domain+'.conf').symlink_to(vhost)
subprocess.run(['nginx','-t'], check=True)
subprocess.run(['systemctl','reload','nginx'], check=True)
body = dict(type='A',name=domain,content='160.250.186.95',ttl=300,proxied=False)
if records:
    if len(records)!=1 or records[0]['type']!='A':
        raise RuntimeError('Unexpected existing DNS records; inspect manually')
    cf(f'zones/{zone}/dns_records/'+records[0]['id'],body,'PUT')
else:
    cf(f'zones/{zone}/dns_records',body,'POST')
print('DNS configured: A -> 160.250.186.95, DNS-only')
