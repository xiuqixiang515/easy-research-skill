#!/usr/bin/env python3
"""Render research notes and validated local card-library summaries."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(os.environ.get("EASY_RESEARCH_DB", Path.home() / ".easy-research" / "cards.json"))
FIELDS = ["来源", "问题", "现有做法", "短板", "可延伸方向", "一句话", "标签", "风险", "最小验证"]

def split_tags(raw: str) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in re.split(r"[,，、;；\s]+", raw or "") if t.strip()))

def read_file(path: str, label: str) -> str:
    p=Path(path)
    try:
        if not p.is_file(): raise ValueError(f"{label}文件不存在或不是普通文件：{path}")
        size=p.stat().st_size
        if size>1_000_000: raise ValueError(f"{label}文件超过1MB限制（实际{size}字节）：{path}")
        return p.read_text(encoding="utf-8-sig").strip()
    except UnicodeError as exc:
        raise ValueError(f"{label}文件必须是UTF-8编码：{path}") from None
    except OSError as exc:
        raise ValueError(f"无法读取{label}文件：{path}（{exc.strerror or exc}）") from None

def validate_cards(value) -> list[dict]:
    if not isinstance(value,list): raise ValueError("卡片库根节点必须是数组")
    seen=set()
    for i,c in enumerate(value,1):
        if not isinstance(c,dict): raise ValueError(f"第{i}张卡片必须是对象")
        ident,title=c.get("id"),c.get("title")
        if not isinstance(ident,str) or not re.fullmatch(r"c\d+",ident): raise ValueError(f"第{i}张卡片的ID无效")
        if ident in seen: raise ValueError(f"卡片ID重复：{ident}")
        seen.add(ident)
        if not isinstance(title,str) or not title.strip(): raise ValueError(f"{ident}缺少有效标题")
        for field in FIELDS+["created","updated"]:
            if not isinstance(c.get(field,""),str): raise ValueError(f"{ident}字段“{field}”必须为文本")
    return value

def load_cards(db:Path)->list[dict]:
    try:
        if not db.is_file(): raise ValueError(f"卡片库不存在或不是文件：{db}")
        text=db.read_text(encoding="utf-8-sig")
        return validate_cards(json.loads(text))
    except json.JSONDecodeError as exc: raise ValueError(f"卡片库JSON损坏（第{exc.lineno}行第{exc.colno}列）：{db}") from None
    except UnicodeError: raise ValueError(f"卡片库必须是UTF-8编码：{db}") from None
    except OSError as exc: raise ValueError(f"无法读取卡片库：{db}（{exc.strerror or exc}）") from None

def content_key(card:dict)->str:
    keys=["title"]+FIELDS
    raw=json.dumps({k:card.get(k,"") for k in keys},sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def table_cell(value) -> str:
    text=str(value or "—").replace("\r\n","\n").replace("\r","\n")
    return text.replace("\\","\\\\").replace("|",r"\|").replace("\n","<br>")

def card_table(cards:list[dict])->str:
    rows=["| ID | 标题/一句话 | 风险 | 标签 |","|---|---|---|---|"]
    for c in cards:
        value=c.get("一句话","").strip() or c["title"]
        rows.append("| "+" | ".join(table_cell(v) for v in [c["id"],value,c.get("风险"),c.get("标签")])+" |")
    return "\n".join(rows)

def weekly_report(cards:list[dict])->list[str]:
    lines=[f"# idea素材库周报（共{len(cards)}张）","",f"*生成时间：{datetime.now().astimezone().isoformat(timespec='minutes')}*","","## 按方向分布","","| 标签 | 卡片数 | 最近更新 |","|---|---:|---|"]
    counts={}
    for c in cards:
        for tag in split_tags(c.get("标签","")):
            entry=counts.setdefault(tag,{"ids":[],"date":""});entry["ids"].append(c["id"])
            entry["date"]=max(entry["date"],c.get("updated") or c.get("created") or "")
    if counts:
        for tag,x in sorted(counts.items(),key=lambda it:(-len(it[1]["ids"]),it[0])):
            lines.append(f"| {table_cell(tag)} | {len(x['ids'])} | {table_cell(x['date'])} |")
    else: lines.append("| （未标记） | 0 | — |")
    gaps={}
    for c in cards:
        g=c.get("短板","").strip()
        if g:gaps.setdefault(g,[]).append(c["id"])
    lines+=["","## 高频短板（完全相同文本出现至少2次）","","| 短板 | 次数 | 卡片 |","|---|---:|---|"]
    repeated=[(g,ids) for g,ids in gaps.items() if len(ids)>=2]
    if repeated:
        for g,ids in sorted(repeated,key=lambda x:(-len(x[1]),x[0])):
            lines.append(f"| {table_cell(g)} | {len(ids)} | {', '.join(ids)} |")
    else: lines.append("| 暂无重复短板 | 0 | — |")
    lines+=["","## 交叉组合线索（仅为待核实的问题，不代表新颖性结论）","","| 标签组合 | 来源卡片 | 待核实的问题 |","|---|---|---|"]
    suggestions={}
    for a,b in itertools.combinations(cards,2):
        if content_key(a)==content_key(b): continue
        for ta in split_tags(a.get("标签","")):
            for tb in split_tags(b.get("标签","")):
                if ta==tb:continue
                key=tuple(sorted((ta,tb)))
                suggestions.setdefault(key,[]).append((a,b))
    if suggestions:
        for (ta,tb),pairs in sorted(suggestions.items()):
            pair=pairs[0]
            lines.append(f"| {table_cell(ta)} × {table_cell(tb)} | {pair[0]['id']}、{pair[1]['id']} | 两方向的限制是否会在同一场景同时发生？先核验机制、相关工作和数据。 |")
    else:lines.append("| 暂无跨标签配对 | — | 需要至少两张带不同标签的卡片 |")
    incomplete=[c for c in cards if not c.get("可延伸方向","").strip()]
    lines+=["","## 待补充（缺少可延伸方向）","","| 卡片 | 已记录短板 | 建议补充 |","|---|---|---|"]
    if incomplete:
        for c in incomplete:lines.append(f"| {c['id']} {table_cell(c['title'])} | {table_cell(c.get('短板'))} | 说明可能的后续方向或写明暂未找到 |")
    else:lines.append("| 暂无 | — | — |")
    dups={}
    for c in cards: dups.setdefault(content_key(c),[]).append(c["id"])
    duplicate_groups=[ids for ids in dups.values() if len(ids)>1]
    lines += ["", "## 重复内容检查", "", "完全相同的卡片不会参与交叉组合；分布与数量仍按库中原始记录显示。"]
    if duplicate_groups:
        lines += ["", "发现疑似重复卡片：" + "; ".join(", ".join(ids) for ids in duplicate_groups) + "。请检查后人工更新或删除。"]
    else:
        lines += ["", "未发现内容完全相同的卡片。"]
    lines += ["", "## 卡片一览","",""+card_table(cards) if cards else "（素材库为空）"]
    return lines

def build(args)->str:
    conclusion=read_file(args.conclusion_file,"结论") if args.conclusion_file else (args.conclusion or "").strip()
    body=read_file(args.body_file,"正文") if args.body_file else (args.body or "").strip()
    appendix=read_file(args.appendix_file,"附录") if args.appendix_file else (args.appendix or "").strip()
    if args.weekly:
        if conclusion or body or appendix or args.next_steps or args.subtitle:
            raise ValueError("--weekly仅生成素材库周报，不与正文参数混用")
        cards=load_cards(Path(args.db))
        lines=weekly_report(cards)
        return "\n".join(lines).rstrip()+"\n"
    parts=[f"# {args.title}",""]
    if args.subtitle:parts += [f"> {args.subtitle}",""]
    parts += [f"*生成时间：{datetime.now().astimezone().isoformat(timespec='minutes')}*",""]
    if conclusion:parts += ["## 结论","",conclusion,""]
    if body:parts += ["## 分析主体","",body,""]
    if args.from_cards:
        cards=load_cards(Path(args.db))
        parts += ["## 候选idea一览","",card_table(cards) if cards else "（素材库为空）",""]
    if args.next_steps:parts += ["## 下一步","",args.next_steps.strip(),""]
    if appendix:parts += ["## 附录：检索记录","",appendix,""]
    if not any((conclusion,body,args.from_cards,args.next_steps,appendix)):
        parts += ["## 草稿提示","","当前只创建了报告标题。请补充正文、结论、下一步或素材库内容后再作为报告使用。",""]
    return "\n".join(parts).rstrip()+"\n"

def same_path(a:Path,b:Path)->bool:
    try:return os.path.normcase(str(a.resolve()))==os.path.normcase(str(b.resolve()))
    except OSError:return False

def main()->int:
    p=argparse.ArgumentParser(description="生成科研分析报告或完整素材库周报")
    p.add_argument("--title",default="科研分析报告")
    p.add_argument("--subtitle")
    p.add_argument("--conclusion",help="结论纯文本")
    p.add_argument("--conclusion-file",help="结论UTF-8文本文件")
    p.add_argument("--body",help="正文纯文本")
    p.add_argument("--body-file",help="正文UTF-8文本文件")
    p.add_argument("--next-steps",help="下一步行动纯文本")
    p.add_argument("--appendix",help="检索附录纯文本")
    p.add_argument("--appendix-file",help="检索附录UTF-8文本文件")
    p.add_argument("--from-cards",action="store_true",help="在报告中附上候选卡片")
    p.add_argument("--weekly",action="store_true",help="按模板生成素材库周报")
    p.add_argument("--db",default=str(DEFAULT_DB))
    p.add_argument("--out",help="输出路径；省略时输出到屏幕")
    p.add_argument("--force",action="store_true",help="覆盖已存在的输出文件（仍禁止覆盖数据库或输入文件）")
    args=p.parse_args()
    if args.conclusion is not None and args.conclusion_file: p.error("--conclusion与--conclusion-file不能同时使用")
    if args.body is not None and args.body_file: p.error("--body与--body-file不能同时使用")
    if args.appendix is not None and args.appendix_file: p.error("--appendix与--appendix-file不能同时使用")
    try:
        text=build(args)
        if not args.out:sys.stdout.write(text);return 0
        out=Path(args.out)
        protected=[Path(args.db)]
        for item in [args.conclusion_file,args.body_file,args.appendix_file]:
            if item:protected.append(Path(item))
        if any(same_path(out,source) for source in protected):
            raise ValueError("输出路径与数据库或输入文件相同，已拒绝写入")
        if out.exists() and not args.force: raise ValueError(f"输出文件已存在：{out}；确认覆盖后加--force")
        if out.exists() and not out.is_file(): raise ValueError(f"输出路径不是普通文件：{out}")
        out.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=f".{out.name}.",suffix=".tmp",dir=out.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:
                f.write(text);f.flush();os.fsync(f.fileno())
            os.replace(tmp,out)
        except BaseException:
            try:os.unlink(tmp)
            except OSError:pass
            raise
        print(f"[已生成] {out}")
        return 0
    except (OSError,UnicodeError,ValueError) as exc:
        print(f"[错误] {exc}",file=sys.stderr);return 2

if __name__=="__main__":
    raise SystemExit(main())
