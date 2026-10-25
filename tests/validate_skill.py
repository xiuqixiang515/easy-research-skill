from pathlib import Path
import re
import yaml

ROOT=Path(__file__).resolve().parents[1]
content=(ROOT/'SKILL.md').read_text(encoding='utf-8-sig')
match=re.match(r'^---\n(.*?)\n---\n',content,re.S)
if not match:raise SystemExit('SKILL.md缺少有效YAML frontmatter')
meta=yaml.safe_load(match.group(1))
if not isinstance(meta,dict) or set(meta)!={'name','description'}:raise SystemExit('frontmatter只允许name和description；版本由VERSION及Git tag管理')
if meta['name']!='easy-research-skill':raise SystemExit('name与Skill目录名不一致')
if not isinstance(meta['description'],str) or not meta['description'].strip() or len(meta['description'])>1024 or '<' in meta['description'] or '>' in meta['description']:
 raise SystemExit('description格式或长度不符合要求')
version=(ROOT/'VERSION').read_text(encoding='ascii').strip()
if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise SystemExit('VERSION必须采用MAJOR.MINOR.PATCH')
changelog=(ROOT/'CHANGELOG.md').read_text(encoding='utf-8-sig')
if f'## {version} ' not in changelog:raise SystemExit('CHANGELOG缺少当前版本记录')
ui=yaml.safe_load((ROOT/'agents/openai.yaml').read_text(encoding='utf-8-sig'))
interface=ui.get('interface',{})
for key in ['display_name','short_description','default_prompt']:
 if not isinstance(interface.get(key),str) or not interface[key].strip():raise SystemExit(f'agents/openai.yaml缺少{key}')
if not 25<=len(interface['short_description'])<=64:raise SystemExit('short_description长度必须为25至64字符')
if '$easy-research-skill' not in interface['default_prompt']:raise SystemExit('default_prompt必须点名$easy-research-skill')
for path in ['scripts/idea_card.py','scripts/report_render.py','references/idea-generation.md','references/demystify.md','references/method-extract.md','references/sharpen.md','references/search-sources.md','references/report-template.md','references/research-types.md','examples/demo-cards.json','examples/demo-report.md']+[f'references/disciplines/{name}.md' for name in ['computer','chemistry','biology','medicine','mechanical','energy','electronics']]:
 if not (ROOT/path).is_file():raise SystemExit(f'缺少资源：{path}')
for py in (ROOT/'scripts').glob('*.py'):
 compile(py.read_text(encoding='utf-8-sig'),str(py),'exec')
print(f'validation passed: {meta["name"]} v{version}; frontmatter, UI metadata, references and Python syntax are valid')
