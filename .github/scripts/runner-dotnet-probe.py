#!/usr/bin/env python3
"""Public, credential-free probe using an isolated copy of the running runner's CLR."""
import hashlib,json,os,pathlib,shutil,subprocess,sys,tempfile
hosts=[f'{a}-{b}-emudhra.we-have-a-problem.com' for b in ['g3b','g3c','g3b-aaa','g3c-aaa'] for a in ['dv','ov','ev']]+['dv-g3b-noct-emudhra.we-have-a-problem.com','dv-g3b-aaa-noct-emudhra.we-have-a-problem.com','api.github.com','codeload.github.com']
workers=[]
for p in pathlib.Path('/proc').glob('[0-9]*'):
 try:
  if (p/'comm').read_text().strip()=='Runner.Worker':workers.append((p/'exe').resolve())
 except OSError:pass
try:
 for line in subprocess.check_output(['ps','-axo','comm='],text=True).splitlines():
  p=pathlib.Path(line.strip())
  if p.is_absolute() and p.name=='Runner.Worker':workers.append(p)
except (OSError,subprocess.CalledProcessError):pass
worker=next((p for p in workers if p.is_file()),None)
def unavailable(reason):
 print(json.dumps({'component':'runner_dotnet_http','qualified':False,'reason':reason,'provider_boundary':'Pre-shell runner downloads are not protected by later job environment changes.'}));sys.exit(0)
if worker is None:unavailable('Running Runner.Worker executable could not be located')
root=worker.parent
if not (root/'System.Private.CoreLib.dll').is_file():unavailable('Runner CLR is not self-contained alongside its apphost')
dotnet=shutil.which('dotnet')
if dotnet is None:unavailable('No installed compiler SDK; no SDK downloaded to manufacture evidence')
env=dict(os.environ,DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1')
work=pathlib.Path(tempfile.mkdtemp(prefix='runner-clr-public-probe-',dir=os.environ['RUNNER_TEMP']))
env['DOTNET_CLI_HOME']=str(work/'sdk-home')
sdks=subprocess.run([dotnet,'--list-sdks'],env=env,capture_output=True,text=True,timeout=20)
choices=[]
for line in sdks.stdout.splitlines():
 try:
  version,base=line.split(' [',1);p=pathlib.Path(base.rstrip(']'))/version/'Roslyn/bincore/csc.dll'
  if p.is_file():choices.append(p)
 except ValueError:pass
if not choices:unavailable('Installed dotnet has no usable C# compiler SDK')
copy=work/'clr';copy.mkdir()
files=[p for p in root.iterdir() if p.is_file() and (p.suffix in ['.dll','.so','.dylib','.json'] or p.name=='Runner.Worker')]
if sum(p.stat().st_size for p in files)>500_000_000:unavailable('Unexpectedly large runtime directory; copy not attempted')
for p in files:shutil.copy2(p,copy/p.name)
source=r'''
using System;
using System.Linq;
using System.Net.Http;
using System.Security.Authentication;
using System.Text.Json;
using System.Threading.Tasks;
public class Program {
 public static int Main(string[] args) {
  var handler = new HttpClientHandler { UseProxy=false, AllowAutoRedirect=false };
  using (handler) using (var client=new HttpClient(handler)) {
   client.Timeout=TimeSpan.FromSeconds(12);
   var tasks=args[0].Split(',').Select(async host=>{
    string result;
    try {
     using(var request=new HttpRequestMessage(HttpMethod.Head,"https://"+host+"/"))
     using(var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead))result="accepted_tls";
    } catch(Exception e) {
     bool certificate=false;
     for(Exception inner=e;inner!=null;inner=inner.InnerException)
      if(inner is AuthenticationException && (inner.Message.IndexOf("certificate",StringComparison.OrdinalIgnoreCase)>=0 || inner.Message.IndexOf("SSL",StringComparison.OrdinalIgnoreCase)>=0))certificate=true;
     result=certificate?"rejected_certificate":"transport_error";
    }
    return new {host,result};
   }).ToArray();
   Task.WaitAll(tasks);
   Console.WriteLine(JsonSerializer.Serialize(new {
    clr=typeof(object).Assembly.GetName().Version.ToString(),
    corelib=typeof(object).Assembly.Location,
    http_assembly=typeof(HttpClient).Assembly.Location,
    handler="HttpClientHandler default certificate verification; no auth/proxy/redirect/body",
    rows=tasks.Select(t=>t.Result).ToArray()
   }));
  }
  return 0;
 }
}
'''
src=work/'probe.cs';src.write_text(source)
refs=[p for p in root.glob('*.dll') if p.name.startswith('System.') or p.name in ['netstandard.dll','mscorlib.dll','Microsoft.CSharp.dll']]
cmd=[dotnet,str(choices[-1]),'-nologo','-noconfig','-nostdlib+','-target:exe','-out:'+str(copy/'Runner.Worker.dll')]+['-r:'+str(p) for p in refs]+[str(src)]
r=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=50)
if r.returncode:unavailable('Bundled-runtime probe compiler rejected references: '+(r.stdout+r.stderr)[-600:])
keys=['SSL_CERT_FILE','SSL_CERT_DIR','CURL_CA_BUNDLE','REQUESTS_CA_BUNDLE','GIT_SSL_CAINFO','PIP_CERT','NODE_OPTIONS','CURL_HOME','GIT_SSL_CAPATH','CARGO_HTTP_CAINFO','HOMEBREW_CURLRC']
raw={k:v for k,v in env.items() if k not in keys}
receipts={}
for phase,case_env in [('raw_runner_store',raw),('scoped_child_store',env)]:
 r=subprocess.run([str(copy/'Runner.Worker'),','.join(hosts)],env=case_env,capture_output=True,text=True,timeout=35)
 if r.returncode:unavailable('Isolated apphost could not execute probe: '+r.stderr[-400:])
 try:result=json.loads(r.stdout)
 except ValueError:unavailable('Isolated apphost returned no usable JSON')
 assert pathlib.Path(result['corelib']).parent==copy and pathlib.Path(result['http_assembly']).parent==copy
 receipts[phase]=result
selected=['Runner.Worker','System.Private.CoreLib.dll','System.Net.Http.dll','System.Net.Security.dll','Runner.Worker.runtimeconfig.json']
print(json.dumps({'component':'runner_dotnet_http','qualified':True,'original_apphost':str(worker),'original_binary_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in selected if (root/n).exists()},'method':'New credential-free assembly compiled against original runner references, run from a copied apphost/CLR; running runner files and process were untouched.','results':receipts,'provider_boundary':'Raw result represents default CLR HTTP verification. Later scoped child env cannot retroactively protect action downloads by the already-running runner.'},sort_keys=True))
