from __future__ import annotations
import concurrent.futures
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
CARD=ROOT/'scripts'/'idea_card.py'
REPORT=ROOT/'scripts'/'report_render.py'
sys.dont_write_bytecode=True
class SkillScriptsTest(unittest.TestCase):
 def setUp(self):
  scratch=ROOT/'.test-tmp'
  scratch.mkdir(exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=scratch)
  self.addCleanup(self.tmp.cleanup)
  self.base=Path(self.tmp.name)
  self.db=self.base/'db'/'cards.json'
  self.env=os.environ.copy()
  self.env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',EASY_RESEARCH_DB=str(self.base/'unused.json'))
 def run_cli(self,script,*args,ok=True):
  p=subprocess.run([sys.executable,'-X','utf8',str(script),'--db',str(self.db),*map(str,args)],cwd=ROOT,env=self.env,capture_output=True,text=True,encoding='utf8',timeout=20)
  self.assertEqual(p.returncode,0 if ok else 2,msg=f"rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
  self.assertNotIn('Traceback',p.stderr)
  return p
 def add(self,title='卡片A',**fields):
  argv=['add','--title',title]
  aliases={'source':'--source','problem':'--problem','current':'--current','gap':'--gap','extend':'--extend','oneline':'--oneline','risk':'--risk','validation':'--validation','tags':'--tags'}
  for key,value in fields.items():argv += [aliases[key],value]
  return self.run_cli(CARD,*argv)
 def cards(self):
  return json.loads(self.db.read_text(encoding='utf8'))
 def test_01_template_and_documented_combine_command(self):
  self.assertIn('- 一句话:',self.run_cli(CARD,'template').stdout)
  self.add('A',gap='gapA',tags='red')
  self.add('B',gap='gapB',tags='blue')
  p=self.run_cli(CARD,'combine','--tag','red','--tag2','blue')
  self.assertIn('c001 × c002',p.stdout)
 def test_02_add_casefold_chinese_search_and_tag(self):
  self.add('多语言',problem='Unicode α与中文',tags='A，B;A')
  self.assertEqual(self.cards()[0]['标签'],'A, B')
  self.assertIn('c001',self.run_cli(CARD,'search','UNICODE').stdout)
  self.assertIn('c001',self.run_cli(CARD,'list','--tag','B').stdout)
 def test_03_duplicate_is_rejected_then_opt_in(self):
  self.add('同内容',problem='p',tags='x')
  self.run_cli(CARD,'add','--title','同内容','--problem','p','--tags','x',ok=False)
  self.run_cli(CARD,'add','--title','同内容','--problem','p','--tags','x','--allow-duplicate')
  self.assertEqual(len(self.cards()),2)
 def test_04_update_preserves_id_and_creates_backup(self):
  self.add('原题',gap='old')
  self.run_cli(CARD,'update','c001','--gap','new')
  self.assertEqual(self.cards()[0]['id'],'c001')
  self.assertEqual(self.cards()[0]['短板'],'new')
  self.assertTrue(Path(str(self.db)+'.bak').exists())
  self.assertEqual(json.loads(Path(str(self.db)+'.bak').read_text(encoding='utf8'))[0]['短板'],'old')
 def test_05_delete_requires_confirmation_and_keeps_backup(self):
  self.add('保留卡',problem='p')
  self.run_cli(CARD,'delete','c001',ok=False)
  self.assertEqual(len(self.cards()),1)
  self.run_cli(CARD,'delete','c001','--yes')
  self.assertEqual(self.cards(),[])
  self.assertEqual(json.loads(Path(str(self.db)+'.bak').read_text(encoding='utf8'))[0]['id'],'c001')
 def test_06_concurrent_adds_do_not_lose_updates(self):
  (self.db.parent).mkdir(parents=True,exist_ok=True)
  args=[]
  for i in range(12):
   args.append([sys.executable,'-X','utf8',str(CARD),'--db',str(self.db),'add','--title',f'parallel-{i}','--problem',f'p-{i}'])
  with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
   results=list(pool.map(lambda cmd:subprocess.run(cmd,cwd=ROOT,env=self.env,capture_output=True,text=True,encoding='utf8',timeout=30),args))
  self.assertTrue(all(p.returncode==0 for p in results),[(p.returncode,p.stderr) for p in results])
  cards=self.cards()
  self.assertEqual(len(cards),12)
  self.assertEqual(len({c['id'] for c in cards}),12)
 def test_07_corrupt_json_is_not_overwritten(self):
  self.db.parent.mkdir(parents=True);self.db.write_text('{broken',encoding='utf8')
  before=self.db.read_bytes()
  p=self.run_cli(CARD,'add','--title','new','--problem','p',ok=False)
  self.assertIn('JSON损坏',p.stderr);self.assertEqual(self.db.read_bytes(),before)
 def test_08_invalid_json_shapes_are_clean_errors(self):
  for raw in ['{}','null','[1]','[{"id":2,"title":"x"}]','[{"id":"c001","title":"x","标签":[]} ]','[{"id":"c001","title":"x"},{"id":"c001","title":"y"}]']:
   self.db.parent.mkdir(parents=True,exist_ok=True);self.db.write_text(raw,encoding='utf8')
   self.run_cli(CARD,'list',ok=False)
 def test_09_utf8_bom_json_and_markdown_continuation(self):
  self.db.parent.mkdir(parents=True,exist_ok=True);self.db.write_text('\ufeff[]',encoding='utf8')
  cardfile=self.base/'card.md'
  cardfile.write_text('\ufeff## BOM标题\n- 问题: 第一行\n  第二行\n- 短板: gap\n',encoding='utf8')
  self.run_cli(CARD,'add','--file',cardfile)
  self.assertEqual(self.cards()[0]['title'],'BOM标题')
  self.assertEqual(self.cards()[0]['问题'],'第一行\n第二行')
 def test_10_multi_card_markdown_rejected_without_mutation(self):
  cardfile=self.base/'two.md';cardfile.write_text('## A\n- 问题: a\n## B\n- 问题: b\n',encoding='utf8')
  self.run_cli(CARD,'add','--file',cardfile,ok=False)
  self.assertFalse(self.db.exists())
 def test_11_empty_search_and_missing_input_are_clean_errors(self):
  self.add('卡',problem='p')
  self.run_cli(CARD,'search','   ',ok=False)
  self.run_cli(CARD,'add','--file',self.base/'missing.md',ok=False)
 def test_12_combine_removes_reverse_duplicates_and_reports_empty(self):
  self.add('A',tags='shared',gap='a')
  self.add('B',tags='shared',gap='b')
  p=self.run_cli(CARD,'combine','--tag','shared','--tag2','shared')
  self.assertEqual(p.stdout.count('## c'),1)
  self.run_cli(CARD,'combine','--tag','absent','--tag2','shared',ok=False)
 def test_13_atomic_replace_failure_preserves_original(self):
  spec=importlib.util.spec_from_file_location('idea_card_under_test',CARD)
  mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
  self.db.parent.mkdir(parents=True,exist_ok=True);self.db.write_text('[{"id":"c001","title":"old"}]',encoding='utf8')
  before=self.db.read_bytes();mod.load(self.db)
  original=mod.os.replace
  def replace(source,target):
   if Path(target)==self.db:raise OSError('injected replace failure')
   return original(source,target)
  with mock.patch.object(mod.os,'replace',side_effect=replace):
   with self.assertRaises(OSError):mod.save(self.db,[{'id':'c001','title':'new'}])
  self.assertEqual(self.db.read_bytes(),before)
 def test_14_report_order_and_markdown_table_escaping(self):
  self.add('含|管道',oneline='一行|两列\n下一行',tags='A|B')
  out=self.base/'report.md'
  self.run_cli(REPORT,'--title','测试','--conclusion','结论','--body','正文','--from-cards','--next-steps','行动','--appendix','检索记录','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertLess(text.index('## 候选idea一览'),text.index('## 下一步'))
  self.assertLess(text.index('## 下一步'),text.index('## 附录：检索记录'))
  self.assertIn(r'\|',text);self.assertIn('<br>',text)
 def test_15_weekly_report_has_required_sections_and_dates(self):
  self.add('A',gap='shared',tags='x',extend='later')
  self.add('B',gap='shared',tags='y',extend='later')
  out=self.base/'weekly.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  for term in ['按方向分布','最近更新','高频短板','交叉组合线索','待补充','c001','c002']:self.assertIn(term,text)
 def test_16_report_cannot_overwrite_database_or_input(self):
  self.add('card',problem='p')
  before=self.db.read_bytes()
  self.run_cli(REPORT,'--from-cards','--out',self.db,ok=False)
  self.assertEqual(self.db.read_bytes(),before)
  body=self.base/'body.md';body.write_text('body',encoding='utf8')
  self.run_cli(REPORT,'--body-file',body,'--out',body,ok=False)
  self.assertEqual(body.read_text(encoding='utf8'),'body')
 def test_17_report_overwrite_requires_force(self):
  out=self.base/'report.md';out.write_text('old',encoding='utf8')
  self.run_cli(REPORT,'--body','new','--out',out,ok=False)
  self.assertEqual(out.read_text(encoding='utf8'),'old')
  self.run_cli(REPORT,'--body','new','--out',out,'--force')
  self.assertIn('new',out.read_text(encoding='utf8'))
 def test_18_text_with_filename_like_suffix_is_plain_text(self):
  p=self.run_cli(REPORT,'--body','Please inspect README.md')
  self.assertIn('Please inspect README.md',p.stdout)
 def test_19_file_errors_and_bad_schema_have_no_traceback(self):
  self.add('x',problem='p')
  self.db.write_text('{"oops":1}',encoding='utf8')
  p=self.run_cli(REPORT,'--from-cards',ok=False)
  self.assertIn('根节点必须是数组',p.stderr)
 def test_20_empty_report_is_marked_as_draft(self):
  p=self.run_cli(REPORT,'--title','草稿')
  self.assertIn('草稿提示',p.stdout)
 def test_21_legacy_duplicate_cards_are_not_cross_combined(self):
  self.db.parent.mkdir(parents=True,exist_ok=True)
  common={'title':'duplicate','来源':'src','问题':'p','现有做法':'m','短板':'g','可延伸方向':'','一句话':'','标签':'red','风险':'中','最小验证':'','created':'2026-01-01','updated':'2026-01-01'}
  self.db.write_text(json.dumps([dict(common,id='c001'),dict(common,id='c002')],ensure_ascii=False),encoding='utf8')
  self.run_cli(CARD,'combine','--tag','red','--tag2','red',ok=False)
  out=self.base/'weekly.md';self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('疑似重复卡片',out.read_text(encoding='utf8'))
 def test_22_imported_markdown_risk_is_validated(self):
   cardfile=self.base/'bad-risk.md'
   cardfile.write_text('## 风险校验\n- 问题: synthetic\n- 风险: 极低\n',encoding='utf8')
   p=self.run_cli(CARD,'add','--file',cardfile,ok=False)
   self.assertIn('风险必须为',p.stderr)
   self.assertFalse(self.db.exists())
 def test_23_unknown_fields_are_preserved_not_dropped(self):
   cardfile=self.base/'meta.md'
   cardfile.write_text('## 催化\n- 问题: 选择性\n  第二行\n- 单位: mol/L\n- 重复: 3批次\n',encoding='utf8')
   p=self.run_cli(CARD,'add','--file',cardfile)
   self.assertIn('单位',p.stdout)
   card=self.cards()[0]
   self.assertEqual(card['扩展'],{'单位':'mol/L','重复':'3批次'})
   self.assertEqual(card['问题'],'选择性\n第二行')
   self.assertIn('单位: mol/L',self.run_cli(CARD,'show','c001').stdout)
 def test_24_set_extra_is_persisted_and_readable_by_weekly_report(self):
   self.add('A',problem='p',tags='x')
   self.run_cli(CARD,'update','c001','--set-extra','温度=室温')
   self.assertEqual(self.cards()[0]['扩展'],{'温度':'室温'})
   out=self.base/'weekly.md'
   self.run_cli(REPORT,'--weekly','--out',out)
   self.assertIn('c001',out.read_text(encoding='utf8'))
 def test_25_extras_distinguish_otherwise_identical_cards(self):
   self.add('A',problem='p')
   p=self.run_cli(CARD,'add','--title','A','--problem','p',ok=False)
   self.assertIn('重复',p.stderr)
   self.run_cli(CARD,'add','--title','A','--problem','p','--set-extra','单位=mol/L')
   self.assertEqual(len(self.cards()),2)
 def test_26_legacy_invalid_risk_survives_unrelated_update(self):
   self.db.parent.mkdir(parents=True,exist_ok=True)
   legacy={'title':'legacy','来源':'','问题':'p','现有做法':'','短板':'','可延伸方向':'','一句话':'','标签':'','风险':'极低','最小验证':'','created':'2026-01-01','updated':'2026-01-01','id':'c001'}
   self.db.write_text(json.dumps([legacy],ensure_ascii=False),encoding='utf8')
   self.run_cli(CARD,'update','c001','--gap','new')
   card=self.cards()[0]
   self.assertEqual(card['短板'],'new')
   self.assertEqual(card['风险'],'极低')
   p=self.run_cli(CARD,'update','c001','--risk','极低',ok=False)
   self.assertIn('invalid choice',p.stderr)
 def test_27_weekly_pairs_are_bounded_per_tag_combination(self):
   for i,tag in enumerate(['red','red','red','blue','blue','blue']):self.add(f'c{i}',problem='p',tags=tag)
   out=self.base/'weekly.md';self.run_cli(REPORT,'--weekly','--out',out)
   text=out.read_text(encoding='utf8')
   self.assertEqual(text.count('| blue × red |')+text.count('| red × blue |'),1)
 def test_28_discipline_and_type_are_stored_and_normalized(self):
  self.run_cli(CARD,'add','--title','卡','--problem','p','--discipline','cs','--research-type','复现')
  card=self.cards()[0]
  self.assertEqual(card['扩展']['学科'],'计算机')
  self.assertEqual(card['扩展']['研究类型'],'复现')
  self.assertIn('学科: 计算机',self.run_cli(CARD,'show','c001').stdout)
 def test_29_invalid_discipline_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','卡','--problem','p','--discipline','天文',ok=False)
  self.assertIn('学科必须为',p.stderr)
  self.assertFalse(self.db.exists())
 def test_30_invalid_research_type_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','卡','--problem','p','--research-type','玄学',ok=False)
  self.assertIn('研究类型必须为',p.stderr)
  self.assertFalse(self.db.exists())
 def test_31_search_covers_extension_values(self):
  self.run_cli(CARD,'add','--title','浓度','--problem','p','--set-extra','单位=mol/L')
  self.assertIn('c001',self.run_cli(CARD,'search','mol/L').stdout)
  self.assertIn('c001',self.run_cli(CARD,'search','单位').stdout)
 def test_32_template_has_meta_lines_and_import_keeps_them_clean(self):
  tpl=self.run_cli(CARD,'template').stdout
  self.assertIn('- 学科:',tpl);self.assertIn('- 研究类型:',tpl)
  cardfile=self.base/'tpl.md';cardfile.write_text(tpl,encoding='utf8')
  self.run_cli(CARD,'add','--file',cardfile)
  self.assertNotIn('扩展',self.cards()[0])
 def test_33_report_table_shows_discipline_column_when_present(self):
  self.run_cli(CARD,'add','--title','卡','--problem','p','--discipline','能源','--research-type','核算')
  out=self.base/'r.md'
  self.run_cli(REPORT,'--title','t','--from-cards','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('学科/类型',text);self.assertIn('能源/核算',text)
 def test_28_discipline_and_type_are_stored_and_normalized(self):
  self.run_cli(CARD,'add','--title','卡','--problem','p','--discipline','cs','--research-type','复现')
  card=self.cards()[0]
  self.assertEqual(card['扩展']['学科'],'计算机')
  self.assertEqual(card['扩展']['研究类型'],'复现')
  self.assertIn('学科: 计算机',self.run_cli(CARD,'show','c001').stdout)
 def test_29_invalid_discipline_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','卡','--problem','p','--discipline','天文',ok=False)
  self.assertIn('学科必须为',p.stderr)
  self.assertFalse(self.db.exists())
 def test_30_invalid_research_type_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','卡','--problem','p','--research-type','玄学',ok=False)
  self.assertIn('研究类型必须为',p.stderr)
  self.assertFalse(self.db.exists())
 def test_31_search_covers_extension_values(self):
  self.run_cli(CARD,'add','--title','浓度','--problem','p','--set-extra','单位=mol/L')
  self.assertIn('c001',self.run_cli(CARD,'search','mol/L').stdout)
  self.assertIn('c001',self.run_cli(CARD,'search','单位').stdout)
 def test_32_template_has_meta_lines_and_import_keeps_them_clean(self):
  tpl=self.run_cli(CARD,'template').stdout
  self.assertIn('- 学科:',tpl);self.assertIn('- 研究类型:',tpl)
  cardfile=self.base/'tpl.md';cardfile.write_text(tpl,encoding='utf8')
  self.run_cli(CARD,'add','--file',cardfile)
  self.assertNotIn('扩展',self.cards()[0])
 def test_33_report_table_shows_discipline_column_when_present(self):
  self.run_cli(CARD,'add','--title','卡','--problem','p','--discipline','能源','--research-type','核算')
  out=self.base/'r.md'
  self.run_cli(REPORT,'--title','t','--from-cards','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('学科/类型',text);self.assertIn('能源/核算',text)
 def test_34_stats_groups_by_research_type(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--research-type','诊断')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--research-type','复现')
  out=self.run_cli(CARD,'stats').stdout
  self.assertIn('按研究类型',out)
  self.assertIn('诊断：1',out)
  self.assertIn('复现：1',out)
 def test_35_list_filters_by_research_type(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--research-type','诊断')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--research-type','复现')
  out=self.run_cli(CARD,'list','--research-type','诊断').stdout
  self.assertIn('甲',out);self.assertNotIn('乙',out)
  p=self.run_cli(CARD,'list','--research-type','玄学',ok=False)
  self.assertIn('研究类型必须为',p.stderr)
 def test_34_stats_groups_by_research_type(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--research-type','诊断')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--research-type','复现')
  out=self.run_cli(CARD,'stats').stdout
  self.assertIn('按研究类型',out)
  self.assertIn('诊断：1',out)
  self.assertIn('复现：1',out)
 def test_35_list_filters_by_research_type(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--research-type','诊断')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--research-type','复现')
  out=self.run_cli(CARD,'list','--research-type','诊断').stdout
  self.assertIn('甲',out);self.assertNotIn('乙',out)
  p=self.run_cli(CARD,'list','--research-type','玄学',ok=False)
  self.assertIn('研究类型必须为',p.stderr)
 def test_36_record_type_is_supported(self):
  self.run_cli(CARD,'add','--title','记录','--problem','p','--research-type','记录')
  self.assertIn('记录：1',self.run_cli(CARD,'stats').stdout)
  self.assertIn('c001',self.run_cli(CARD,'list','--research-type','记录').stdout)
 def test_37_valid_units_are_accepted(self):
  for i,unit in enumerate(['mol/L','MPa/mm','dBFS','bit; dBFS']):
   self.run_cli(CARD,'add','--title',f'u{i}','--problem','p','--set-extra',f'单位={unit}')
  self.assertIn('卡片总数：4',self.run_cli(CARD,'stats').stdout)
 def test_38_chinese_unit_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','x','--problem','p','--set-extra','单位=个/批',ok=False)
  self.assertIn('单位不应包含中文',p.stderr)
  self.assertFalse(self.db.exists())
 def test_39_unparsable_unit_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','x','--problem','p','--set-extra','单位=about 3 grams',ok=False)
  self.assertIn('单位格式无法识别',p.stderr)
  self.assertFalse(self.db.exists())
 def test_40_bad_unit_update_rolls_back(self):
  self.run_cli(CARD,'add','--title','ok','--problem','p','--set-extra','单位=mol/L')
  p=self.run_cli(CARD,'update','c001','--set-extra','单位=个/批',ok=False)
  self.assertIn('单位不应包含中文',p.stderr)
  self.assertEqual(self.cards()[0]['扩展']['单位'],'mol/L')
 def test_36_record_type_is_supported(self):
  self.run_cli(CARD,'add','--title','记录','--problem','p','--research-type','记录')
  self.assertIn('记录：1',self.run_cli(CARD,'stats').stdout)
  self.assertIn('c001',self.run_cli(CARD,'list','--research-type','记录').stdout)
 def test_37_valid_units_are_accepted(self):
  for i,unit in enumerate(['mol/L','MPa/mm','dBFS','bit; dBFS']):
   self.run_cli(CARD,'add','--title',f'u{i}','--problem','p','--set-extra',f'单位={unit}')
  self.assertIn('卡片总数：4',self.run_cli(CARD,'stats').stdout)
 def test_38_chinese_unit_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','x','--problem','p','--set-extra','单位=个/批',ok=False)
  self.assertIn('单位不应包含中文',p.stderr)
  self.assertFalse(self.db.exists())
 def test_39_unparsable_unit_is_rejected(self):
  p=self.run_cli(CARD,'add','--title','x','--problem','p','--set-extra','单位=about 3 grams',ok=False)
  self.assertIn('单位格式无法识别',p.stderr)
  self.assertFalse(self.db.exists())
 def test_40_bad_unit_update_rolls_back(self):
  self.run_cli(CARD,'add','--title','ok','--problem','p','--set-extra','单位=mol/L')
  p=self.run_cli(CARD,'update','c001','--set-extra','单位=个/批',ok=False)
  self.assertIn('单位不应包含中文',p.stderr)
  self.assertEqual(self.cards()[0]['扩展']['单位'],'mol/L')
 def test_41_cards_carrying_both_tags_are_not_paired_with_themselves(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','x, y')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','x')
  self.run_cli(CARD,'add','--title','丙','--problem','r','--tags','y')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('c002、c003',text)
  self.assertNotIn('c001、c002',text)
 def test_41_cards_carrying_both_tags_are_not_paired_with_themselves(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','x, y')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','x')
  self.run_cli(CARD,'add','--title','丙','--problem','r','--tags','y')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('c002、c003',text)
  self.assertNotIn('c001、c002',text)
 def test_42_conflicting_units_are_reported(self):
  self.run_cli(CARD,'add','--title','楼A评估','--problem','p','--tags','楼A, 节能','--discipline','能源','--set-extra','功能单位=kWh/m2/a')
  self.run_cli(CARD,'add','--title','楼A复核','--problem','q','--tags','楼A, 节能','--discipline','能源','--set-extra','功能单位=kWh/床/a')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('口径冲突',text)
  self.assertIn('kWh/m2/a / kWh/床/a',text)
 def test_43_same_values_are_not_reported(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','楼A','--discipline','能源','--set-extra','功能单位=kWh/m2/a')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','楼A','--discipline','能源','--set-extra','功能单位=kWh/m2/a')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('未发现并存口径',out.read_text(encoding='utf8'))
 def test_44_different_projects_are_not_paired(self):
  self.run_cli(CARD,'add','--title','楼A','--problem','p','--tags','楼A','--discipline','能源','--set-extra','边界=使用阶段')
  self.run_cli(CARD,'add','--title','楼B','--problem','q','--tags','楼B','--discipline','能源','--set-extra','边界=全生命周期')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('未发现并存口径',out.read_text(encoding='utf8'))
 def test_42_conflicting_units_are_reported(self):
  self.run_cli(CARD,'add','--title','楼A评估','--problem','p','--tags','楼A, 节能','--discipline','能源','--set-extra','功能单位=kWh/m2/a')
  self.run_cli(CARD,'add','--title','楼A复核','--problem','q','--tags','楼A, 节能','--discipline','能源','--set-extra','功能单位=kWh/床/a')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('口径冲突',text)
  self.assertIn('kWh/m2/a / kWh/床/a',text)
 def test_43_same_values_are_not_reported(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','楼A','--discipline','能源','--set-extra','功能单位=kWh/m2/a')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','楼A','--discipline','能源','--set-extra','功能单位=kWh/m2/a')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('未发现并存口径',out.read_text(encoding='utf8'))
 def test_44_different_projects_are_not_paired(self):
  self.run_cli(CARD,'add','--title','楼A','--problem','p','--tags','楼A','--discipline','能源','--set-extra','边界=使用阶段')
  self.run_cli(CARD,'add','--title','楼B','--problem','q','--tags','楼B','--discipline','能源','--set-extra','边界=全生命周期')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('未发现并存口径',out.read_text(encoding='utf8'))
 def test_45_same_project_without_shared_tags_is_compared(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','方向A','--discipline','能源','--set-extra','项目=楼A','--set-extra','功能单位=kWh/m2/a')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','方向B','--discipline','能源','--set-extra','项目=楼A','--set-extra','功能单位=kWh/m2/月')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('kWh/m2/a / kWh/m2/月',text)
  self.assertIn('楼A',text)
 def test_46_different_projects_are_not_compared(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','节能','--discipline','能源','--set-extra','项目=楼A','--set-extra','边界=使用阶段')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','节能','--discipline','能源','--set-extra','项目=楼B','--set-extra','边界=全生命周期')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('未发现并存口径',out.read_text(encoding='utf8'))
 def test_47_umbrella_tag_does_not_merge_projects(self):
  for project,unit in (('甲项目','kWh/m2/a'),('乙项目','kWh/床/a'),('丙项目','kWh/a'),('丁项目','kWh/t')):
   for i in range(3):
    if project=='甲项目' and i==2: unit_value='kWh/m2/月'
    else: unit_value=unit
    self.run_cli(CARD,'add','--title',f'{project}-{i}','--problem','p','--tags',f'{project}, 节能','--discipline','能源','--set-extra','功能单位='+unit_value)
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('kWh/m2/a / kWh/m2/月',text)
  self.assertNotIn('kWh/床/a',text)
 def test_45_same_project_without_shared_tags_is_compared(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','方向A','--discipline','能源','--set-extra','项目=楼A','--set-extra','功能单位=kWh/m2/a')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','方向B','--discipline','能源','--set-extra','项目=楼A','--set-extra','功能单位=kWh/m2/月')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('kWh/m2/a / kWh/m2/月',text)
  self.assertIn('楼A',text)
 def test_46_different_projects_are_not_compared(self):
  self.run_cli(CARD,'add','--title','甲','--problem','p','--tags','节能','--discipline','能源','--set-extra','项目=楼A','--set-extra','边界=使用阶段')
  self.run_cli(CARD,'add','--title','乙','--problem','q','--tags','节能','--discipline','能源','--set-extra','项目=楼B','--set-extra','边界=全生命周期')
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  self.assertIn('未发现并存口径',out.read_text(encoding='utf8'))
 def test_47_umbrella_tag_does_not_merge_projects(self):
  for project,unit in (('甲项目','kWh/m2/a'),('乙项目','kWh/床/a'),('丙项目','kWh/a'),('丁项目','kWh/t')):
   for i in range(3):
    if project=='甲项目' and i==2: unit_value='kWh/m2/月'
    else: unit_value=unit
    self.run_cli(CARD,'add','--title',f'{project}-{i}','--problem','p','--tags',f'{project}, 节能','--discipline','能源','--set-extra','功能单位='+unit_value)
  out=self.base/'w.md'
  self.run_cli(REPORT,'--weekly','--out',out)
  text=out.read_text(encoding='utf8')
  self.assertIn('kWh/m2/a / kWh/m2/月',text)
  self.assertNotIn('kWh/床/a',text)
if __name__=='__main__':unittest.main(verbosity=2)
