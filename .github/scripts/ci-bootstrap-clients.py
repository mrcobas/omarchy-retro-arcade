#!/usr/bin/env python3
"""Finite, credential-free actual downloader checks; all state uses job scratch."""
import concurrent.futures,json,os,pathlib,re,shutil,subprocess,tempfile
hosts=[f'{a}-{b}-emudhra.we-have-a-problem.com' for b in ['g3b','g3c','g3b-aaa','g3c-aaa'] for a in ['dv','ov','ev']]+['dv-g3b-noct-emudhra.we-have-a-problem.com','dv-g3b-aaa-noct-emudhra.we-have-a-problem.com']
scratch=pathlib.Path(tempfile.mkdtemp(prefix='ci-bootstrap-clients-',dir=os.environ['RUNNER_TEMP']))
pattern=re.compile(r'CERTIFICATE_VERIFY_FAILED|SSL certificate problem|SSL certificate OpenSSL verify result|invalid peer certificate|certificate verify failed|certificate has been revoked|certificate is revoked|InvalidCertificate|UnknownIssuer|UntrustedRoot|certificate is blocked',re.I)
versions={};rows=[]
for tool in ['cargo','rustup','mise']:
 binary=shutil.which(tool)
 if not binary:continue
 version=subprocess.run([binary,'--version'],capture_output=True,text=True,timeout=15)
 versions[tool]={'path':binary,'version':version.stdout.splitlines()[0] if version.stdout else 'unknown'}
 def one(host):
  state=scratch/(tool+'-'+host);state.mkdir();(state/'config.toml').write_text('')
  env=dict(os.environ)
  if tool=='cargo':
   env.update(CARGO_HOME=str(state),CARGO_NET_RETRY='0',CARGO_HTTP_TIMEOUT='10')
   args=[binary,'search','serde','--registry','ci_probe','--limit','1','--config',f'registries.ci_probe.index="sparse+https://{host}/"']
  elif tool=='rustup':
   env.update(RUSTUP_DIST_SERVER='https://'+host)
   args=[binary,'check','--no-self-update']
  else:
   env.update(MISE_NODE_MIRROR_URL='https://'+host,XDG_CACHE_HOME=str(state/'cache'),MISE_CACHE_DIR=str(state/'cache'),MISE_STATE_DIR=str(state/'state'),MISE_CONFIG_DIR=str(state/'config'),MISE_USE_VERSIONS_HOST='0',MISE_NO_SELF_UPDATE='1',MISE_DATA_DIR=str(state/'data'),MISE_GLOBAL_CONFIG_FILE=str(state/'config.toml'),MISE_HTTP_TIMEOUT='10s',MISE_HTTP_RETRIES='0')
   args=[binary,'ls-remote','--no-versions-host','node']
  try:
   r=subprocess.run(args,env=env,cwd=state,capture_output=True,text=True,timeout=25)
   return {'tool':tool,'host':host,'result':'rejected_certificate' if pattern.search(r.stderr+r.stdout) else 'not_certificate_rejection','exit':r.returncode,**({'error_excerpt':r.stderr[-500:]} if host==hosts[0] else {})}
  except subprocess.TimeoutExpired:return {'tool':tool,'host':host,'result':'transport_timeout'}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:group=list(pool.map(one,hosts))
 rows.extend(group)
 # Real provider path proves this caller can still fetch ordinary metadata.
 state=scratch/(tool+'-positive');state.mkdir();(state/'config.toml').write_text('');env=dict(os.environ)
 if tool=='cargo':
  env.update(CARGO_HOME=str(state),CARGO_NET_RETRY='0',CARGO_HTTP_TIMEOUT='15');args=[binary,'search','serde','--limit','1'];provider='index.crates.io + crates.io API'
 elif tool=='rustup':
  args=[binary,'check','--no-self-update'];provider='static.rust-lang.org rustup release metadata'
 else:
  env.update(XDG_CACHE_HOME=str(state/'cache'),MISE_CACHE_DIR=str(state/'cache'),MISE_STATE_DIR=str(state/'state'),MISE_CONFIG_DIR=str(state/'config'),MISE_USE_VERSIONS_HOST='0',MISE_NO_SELF_UPDATE='1',MISE_DATA_DIR=str(state/'data'),MISE_GLOBAL_CONFIG_FILE=str(state/'config.toml'),MISE_HTTP_TIMEOUT='15s',MISE_HTTP_RETRIES='0');args=[binary,'ls-remote','--no-versions-host','node'];provider='nodejs.org release metadata'
 try:
  r=subprocess.run(args,env=env,cwd=state,capture_output=True,text=True,timeout=30)
  rows.append({'tool':tool,'positive_provider':provider,'result':'accepted_tls' if r.returncode in ([0,100] if tool=='rustup' else [0]) else 'provider_check_failed','exit':r.returncode,**({'error_excerpt':r.stderr[-500:]} if r.returncode not in [0,100] else {})})
 except subprocess.TimeoutExpired:rows.append({'tool':tool,'positive_provider':provider,'result':'transport_timeout'})
print(json.dumps({'component':'actual_ci_bootstrap_clients','versions':versions,'rows':rows,'method':'Actual readonly registry/version/check commands with per-probe empty state; no package/toolchain install, auth, source data or response bodies retained.'},sort_keys=True))
assert versions, 'No actual bootstrap clients found'
assert all(r['result']==('accepted_tls' if 'positive_provider' in r else 'rejected_certificate') for r in rows), 'Bootstrap downloader TLS acceptance is incomplete'
