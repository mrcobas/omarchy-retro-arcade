#!/usr/bin/env python3
"""Actual Git HTTPS rejection with no credential helper, auth, cookies or checkout."""
import concurrent.futures,json,os,pathlib,re,shutil,subprocess,tempfile
assert not (pathlib.Path.home()/'.netrc').exists(), 'Refuse a fixture probe with ambient netrc credentials'
git=shutil.which('git');assert git
hosts=[f'{a}-{b}-emudhra.we-have-a-problem.com' for b in ['g3b','g3c','g3b-aaa','g3c-aaa'] for a in ['dv','ov','ev']]+['dv-g3b-noct-emudhra.we-have-a-problem.com','dv-g3b-aaa-noct-emudhra.we-have-a-problem.com']
env={k:v for k,v in os.environ.items() if not k.startswith('GIT_TRACE') and k not in ['GIT_CURL_VERBOSE','GIT_CONFIG_PARAMETERS','GIT_CONFIG_COUNT','GIT_SSL_NO_VERIFY']}
env.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',GIT_ASKPASS='/usr/bin/false',SSH_ASKPASS='/usr/bin/false',GCM_INTERACTIVE='never')
base=[git,'-c','credential.helper=','-c','http.extraHeader=','-c','http.cookieFile=','-c','http.saveCookies=false','-c','http.sslVerify=true']
certificate=re.compile(r'certificate verification failed|SSL certificate problem|SSL certificate OpenSSL verify result|server certificate verification failed|certificate verify failed|certificate is not trusted|SSL peer certificate',re.I)
with tempfile.TemporaryDirectory(prefix='git-tls-public-',dir=os.environ.get('RUNNER_TEMP')) as scratch:
 def one(host):
  try:
   r=subprocess.run(base+['ls-remote','https://'+host+'/fixture.git','HEAD'],cwd=scratch,env=env,capture_output=True,text=True,timeout=15)
   result='rejected_certificate' if certificate.search(r.stderr) else 'not_certificate_rejection'
   return {'host':host,'result':result,'exit':r.returncode,**({'error_excerpt':r.stderr[-300:]} if result!='rejected_certificate' else {})}
  except subprocess.TimeoutExpired:return {'host':host,'result':'transport_timeout'}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,hosts))
 r=subprocess.run(base+['ls-remote','https://github.com/actions/checkout.git','HEAD'],cwd=scratch,env=env,capture_output=True,text=True,timeout=20)
 positive=r.returncode==0 and bool(re.match(r'^[0-9a-f]{40}\s+HEAD\s*$',r.stdout.strip()))
 version=subprocess.check_output([git,'--version'],text=True).strip()
 print(json.dumps({'component':'actual_git_https','git':version,'executable':git,'rows':rows,'normal_public_github_ref':positive,'credential_helper':'disabled','extra_headers_cookies':'disabled','home_netrc_absent':True,'response_body_retained':False},sort_keys=True))
 assert all(r['result']=='rejected_certificate' for r in rows), 'Actual Git HTTPS rejection incomplete'
 assert positive, 'Ordinary public GitHub ref lookup failed'
