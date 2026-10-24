from pathlib import Path
import subprocess,sys,json,time,hashlib,platform
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent
WORK=OUT/'temp-data'
WORK.mkdir(exist_ok=True)
records=[]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
tracked=[ROOT/'SKILL.md',*(ROOT/'references').glob('*.md'),*(ROOT/'scripts').glob('*.py')]
before={str(p.relative_to(ROOT)):sha(p) for p in tracked}
def run(case,script,args,expected,check):
 cmd=[sys.executable,'-X','utf8',str(ROOT/'scripts'/script),*map(str,args)]
 start=time.perf_counter()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=30)
  result={'case':case,'command_argv':cmd,'cwd':str(ROOT),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'seconds':time.perf_counter()-start,'expected':expected}
  result['passed']=bool(check(p))
 except subprocess.TimeoutExpired:
  result={'case':case,'command_argv':cmd,'cwd':str(ROOT),'exit_code':None,'stdout':'','stderr':'timeout after 30 seconds','seconds':time.perf_counter()-start,'expected':expected,'passed':False}
 records.append(result)
 return result
domains=[
 ('computer','计算机','F1=0.81; seed=42; split=user', '用户分组'),
 ('chemistry','化学','c=0.10 mol/L; T=298 K; yield=82%; batch=A', '独立批次'),
 ('biology','生物','n_bio=3; n_tech=2; ΔCt=-1.2; gene=TP53', '生物重复'),
 ('medicine','医学','synthetic only; AUC=0.81; 95% CI=[0.72,0.90]; t0=admission', '时间外验证'),
 ('mechanical','机械','σ=120 MPa; δ=0.20 mm; mass=0.50 kg; mesh=1 mm', '网格收敛'),
 ('energy','能源','η=0.82; E=10 kWh; boundary=system; SOC0=SOC1', '系统边界'),
 ('electronics','电子信息','SNR=10 dB; fs=20 MHz; BW=5 MHz; BER=1e-3', '采样条件')]
for slug,name,content,keyword in domains:
 db=WORK/(slug+'.json')
 # A fresh uniquely scoped database is required on each harness execution.
 if db.exists(): raise SystemExit('Refusing reuse of existing database: '+str(db))
 common=['--db',db]
 for i,tag in [(1,'constraint'),(2,'method')]:
  run(slug+'.add'+str(i),'idea_card.py',common+['add','--title',name+str(i),'--problem',content,'--gap',keyword,'--source','synthetic fixture; not real evidence','--validation','units retained; expert review pending','--tags',slug+','+tag],
   'exit 0; card stored',lambda p:p.returncode==0)
 run(slug+'.search','idea_card.py',common+['search',keyword],'exit 0; both cards found',lambda p:p.returncode==0 and 'c001' in p.stdout and 'c002' in p.stdout)
 run(slug+'.show','idea_card.py',common+['show','c001'],'exit 0; exact scientific text retained',lambda p:p.returncode==0 and content in p.stdout)
 run(slug+'.combine','idea_card.py',common+['combine','--tag','constraint','--tag2','method'],'exit 0; one distinct pair',lambda p:p.returncode==0 and p.stdout.count('## c')==1)
 oldhash=sha(db)
 run(slug+'.duplicate','idea_card.py',common+['add','--title',name+'1','--problem',content,'--gap',keyword,'--source','synthetic fixture; not real evidence','--validation','units retained; expert review pending','--tags',slug+',constraint'],
   'exit 2; duplicate rejected; database unchanged',lambda p:p.returncode==2 and sha(db)==oldhash)
 stable=[]
 for repeat in range(3):
  r=run(slug+'.weekly'+str(repeat+1),'report_render.py',common+['--weekly'],'exit 0; all sections present; evidence text not altered in DB',lambda p:p.returncode==0 and '按方向分布' in p.stdout and '待补充' in p.stdout and sha(db)==oldhash)
  stable.append('\n'.join(line for line in r['stdout'].splitlines() if not line.startswith('*生成时间')))
 records.append({'case':slug+'.repeat_consistency','expected':'three normalized weekly outputs identical','passed':len(set(stable))==1,'command_argv':[],'exit_code':None,'stdout':'normalized hashes: '+str([hashlib.sha256(t.encode()).hexdigest() for t in stable]),'stderr':''})
 stored=json.loads(db.read_text(encoding='utf-8'))
 assert len(stored)==2 and all(c['问题']==content for c in stored)
# New contract probes: compare actual behavior with the declared CLI contract.
db=WORK/'probes.json'
bad=WORK/'bad-risk.md'
bad.write_text('## 风险校验\n- 问题: synthetic\n- 风险: 极低\n',encoding='utf-8')
run('probe.invalid_markdown_risk','idea_card.py',['--db',db,'add','--file',bad],'exit 2; invalid risk from Markdown rejected',lambda p:p.returncode==2)
extra=WORK/'metadata.md'
extra.write_text('## 单位元数据\n- 问题: 比较两组浓度\n- 单位: mol/L\n- 风险: 中\n',encoding='utf-8')
run('probe.unknown_markdown_field','idea_card.py',['--db',db,'add','--file',extra],'unknown scientific field must be preserved or explicit warning/error emitted',lambda p:p.returncode!=0 or '单位' in p.stderr or 'mol/L' in db.read_text(encoding='utf-8'))
# Local scaling only, synthetic single-tag cards; this is not Agent response speed.
for n in [100,500,1000]:
 large=WORK/('scale-'+str(n)+'.json')
 cards=[{'id':f'c{i+1:04d}','title':f'fixture-{i}','标签':'a' if i%2 else 'b','短板':'synthetic','可延伸方向':'pending'} for i in range(n)]
 large.write_text(json.dumps(cards),encoding='utf-8')
 run('scale.weekly.'+str(n),'report_render.py',['--db',large,'--weekly'],'exit 0 within 30 second test budget',lambda p:p.returncode==0)
after={str(p.relative_to(ROOT)):sha(p) for p in tracked}
summary={'platform':platform.platform(),'python':sys.version,'executions':sum(bool(r.get('command_argv')) for r in records),'checks':len(records),'passed':sum(r['passed'] for r in records),'failed':[r['case'] for r in records if not r['passed']],'source_unchanged':before==after,'source_hashes':before,'benchmarks':[{k:r[k] for k in ['case','seconds','exit_code']} for r in records if r['case'].startswith('scale.')]}
(OUT/'cli-results.json').write_text(json.dumps({'summary':summary,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=True,indent=2))

