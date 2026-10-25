#!/usr/bin/env python3
"""Local research idea-card library with validation and atomic mutations."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(os.environ.get("EASY_RESEARCH_DB", Path.home() / ".easy-research" / "cards.json"))
FIELDS = ["来源", "问题", "现有做法", "短板", "可延伸方向", "一句话", "标签", "风险", "最小验证"]
EXTRA = "扩展"
LOCK_TIMEOUT = 30.0
LOCK_RETRY_INTERVAL = 0.05
DISCIPLINES = {"计算机", "化学", "生物", "医学", "机械", "能源", "电子信息"}
DISCIPLINE_ALIASES = {
    "cs": "计算机", "计算机科学": "计算机", "chemistry": "化学", "biology": "生物",
    "medicine": "医学", "mechanical": "机械", "energy": "能源",
    "electronics": "电子信息", "电子": "电子信息", "信息": "电子信息",
}
RESEARCH_TYPES = {"预测", "因果", "实验", "仿真", "理论", "描述性", "复现", "工程验证", "核算", "诊断"}
ALIASES = {
    "source": "来源", "problem": "问题", "current": "现有做法",
    "gap": "短板", "extend": "可延伸方向", "oneline": "一句话",
    "risk": "风险", "validation": "最小验证",
}
RISK_VALUES = {"低", "中", "高"}
TEMPLATE = """## 标题
一句话说清做什么

- 来源:
- 问题:
- 现有做法:
- 短板:
- 可延伸方向:
- 一句话:
- 学科:
- 研究类型:
- 标签:
- 风险: 中
- 最小验证:
"""
def stamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def tags(raw: str) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in re.split(r"[,，、;；\s]+", raw or "") if t.strip()))

def load(db: Path) -> list[dict]:
    if not db.exists():
        return []
    try:
        cards = json.loads(db.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"卡片库JSON损坏（第{exc.lineno}行第{exc.colno}列）：{db}") from None
    if not isinstance(cards, list):
        raise ValueError("卡片库根节点必须是数组")
    seen: set[str] = set()
    for i, card in enumerate(cards, 1):
        if not isinstance(card, dict):
            raise ValueError(f"第{i}张卡片必须是对象")
        ident, title = card.get("id"), card.get("title")
        if not isinstance(ident, str) or not re.fullmatch(r"c\d+", ident):
            raise ValueError(f"第{i}张卡片的id必须是c加数字的字符串")
        if ident in seen:
            raise ValueError(f"第{i}张卡片ID重复：{ident}")
        seen.add(ident)
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"{ident}的title必须是非空字符串")
        for key in FIELDS + ["created", "updated"]:
            value = card.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"{ident}的字段“{key}”必须是字符串")
        extra = card.get(EXTRA, {})
        if not isinstance(extra, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in extra.items()):
            raise ValueError(f"{ident}的字段“{EXTRA}”必须是从文本到文本的映射")
    return cards

@contextlib.contextmanager
def mutation_lock(db: Path):
    """Lock read-modify-write across processes on Windows and POSIX."""
    db.parent.mkdir(parents=True, exist_ok=True)
    path = Path(str(db) + ".lock")
    with _open_lock_file(path) as f:
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + LOCK_TIMEOUT
            while True:
                try:
                    f.seek(0, os.SEEK_END)
                    if f.tell() == 0:
                        f.write(b"\0"); f.flush()
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1); break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("等待卡片库锁超时") from None
                    time.sleep(LOCK_RETRY_INTERVAL)
            try: yield
            finally:
                with contextlib.suppress(OSError):
                    f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def _open_lock_file(path: Path):
    """Open the lock file, retrying transient Windows sharing violations (EACCES)."""
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            return path.open("a+b")
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"无法打开卡片库锁文件：{path}（{exc.strerror or exc}）") from None
            time.sleep(LOCK_RETRY_INTERVAL)

def _atomic_bytes(path: Path, data: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(OSError): os.unlink(temp_name)
        raise

def save(db: Path, cards: list[dict]) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(cards, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if db.exists():
        backup = Path(str(db) + ".bak")
        fd, temp_name = tempfile.mkstemp(prefix=f".{backup.name}.", suffix=".tmp", dir=db.parent)
        try:
            with os.fdopen(fd, "wb") as target, db.open("rb") as source:
                shutil.copyfileobj(source, target); target.flush(); os.fsync(target.fileno())
            os.replace(temp_name, backup)
        except BaseException:
            with contextlib.suppress(OSError): os.unlink(temp_name)
            raise
    _atomic_bytes(db, data)

def next_id(cards: list[dict]) -> str:
    numbers = [int(c["id"][1:]) for c in cards]
    return f"c{max(numbers, default=0)+1:03d}"

def content_key(card: dict) -> str:
    fields = {k: card.get(k, "") for k in ["title"] + FIELDS}
    fields[EXTRA] = card.get(EXTRA) or {}
    raw = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def haystack(card: dict) -> str:
    """Searchable text: standard fields plus extension keys and values."""
    parts = [str(card.get(k, "")) for k in ["title"] + FIELDS]
    extra = card.get(EXTRA) or {}
    parts.extend(str(k) for k in extra)
    parts.extend(str(v) for v in extra.values())
    return " ".join(parts).casefold()

def check_risk(card: dict) -> None:
    """Write-path guard: the risk field must use the documented enum, whatever its source."""
    risk = (card.get("风险") or "").strip()
    if risk and risk not in RISK_VALUES:
        raise ValueError(f"风险必须为：{'、'.join(sorted(RISK_VALUES))}（当前值：{risk}）")

def normalize_discipline(value: str) -> str:
    value = (value or "").strip()
    return DISCIPLINE_ALIASES.get(value.lower(), value)

def check_meta(card: dict) -> None:
    """Validate discipline and research type stored in the extension object."""
    extra = card.get(EXTRA) or {}
    discipline = normalize_discipline(extra.get("学科", ""))
    if discipline and discipline not in DISCIPLINES:
        raise ValueError(f"学科必须为：{'、'.join(sorted(DISCIPLINES))}（当前值：{extra.get('学科')}）")
    if discipline:
        extra["学科"] = discipline
    research = (extra.get("研究类型") or "").strip()
    if research and research not in RESEARCH_TYPES:
        raise ValueError(f"研究类型必须为：{'、'.join(sorted(RESEARCH_TYPES))}（当前值：{research}）")
    if extra:
        card[EXTRA] = extra

def parse_extra(items: list[str] | None, base: dict | None = None) -> dict:
    extra = dict(base or {})
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"自定义字段需要KEY=VALUE形式：{item}")
        extra[key.strip()] = value.strip()
    return extra

def parse_card(text: str) -> dict:
    lines = text.lstrip("\ufeff").splitlines()
    headings = [(i, line[3:].strip()) for i, line in enumerate(lines) if line.startswith("## ")]
    if len(headings) > 1:
        raise ValueError("每次只能导入一张Markdown卡片；检测到多个二级标题")
    card = {field: "" for field in FIELDS}
    extra: dict[str, str] = {}
    title = headings[0][1] if headings else ""
    current = None
    for line in lines:
        match = re.match(r"^\s*[-*]\s*([^:：]+)[:：]\s*(.*)$", line)
        if match:
            key = match.group(1).strip()
            if key in card:
                current = (card, key)
                card[key] = match.group(2).strip()
            else:
                current = (extra, key)
                extra[key] = match.group(2).strip()
        elif current and line[:1].isspace() and line.strip():
            target, key = current
            target[key] += ("\n" if target[key] else "") + line.strip()
        else:
            current = None
            if not title and line.strip() and not line.lstrip().startswith(("-", "*", "#")):
                title = line.strip()
    if not title:
        raise ValueError("卡片缺少标题（Markdown格式请使用“## 标题”）")
    card["title"] = title
    extra = {k: v for k, v in extra.items() if v.strip()}
    if extra:
        card[EXTRA] = extra
    return card

def add_card(args) -> None:
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8-sig")
        card = parse_card(text)
    else:
        card = {field: "" for field in FIELDS}
        card["title"] = args.title or ""
    if args.title: card["title"] = args.title
    for name, field in ALIASES.items():
        value = getattr(args, name, None)
        if value is not None: card[field] = value
    if args.tags is not None: card["标签"] = args.tags
    if args.tag: card["标签"] = ", ".join(dict.fromkeys(tags(card.get("标签", "")) + tags(args.tag)))
    if args.set_extra:
        card[EXTRA] = parse_extra(args.set_extra, card.get(EXTRA))
    if args.discipline or args.research_type:
        extra = dict(card.get(EXTRA) or {})
        if args.discipline: extra["学科"] = args.discipline
        if args.research_type: extra["研究类型"] = args.research_type
        card[EXTRA] = extra
    check_risk(card)
    check_meta(card)
    card["标签"] = ", ".join(tags(card.get("标签", "")))
    if not card.get("title","").strip():
        raise ValueError("新增卡片至少需要标题；可先用template创建卡片文件")
    if not any(card.get(k) for k in FIELDS) and not card.get(EXTRA):
        raise ValueError("新增卡片至少需要一个内容字段")
    with mutation_lock(Path(args.db)):
        cards = load(Path(args.db))
        fingerprint = content_key(card)
        duplicate = next((c for c in cards if content_key(c) == fingerprint), None)
        if duplicate and not args.allow_duplicate:
            raise ValueError(f"内容与{duplicate['id']}重复；若确需保留副本，请使用--allow-duplicate")
        card["id"] = next_id(cards); card["created"] = stamp(); card["updated"] = card["created"]
        cards.append(card); save(Path(args.db), cards)
    print(f"[已添加] {card['id']}  {card['title']}")
    if card.get(EXTRA):
        print(f"[已保留自定义字段] {'、'.join(card[EXTRA])}")

def update_card(args) -> None:
    updates = {}
    if args.title is not None: updates["title"] = args.title
    for name, field in ALIASES.items():
        value = getattr(args, name, None)
        if value is not None: updates[field] = value
    if args.tags is not None: updates["标签"] = args.tags
    if args.tag is not None:
        # append after reading the current tags in the locked transaction
        updates["_append_tags"] = args.tag
    if args.set_extra:
        updates["_set_extra"] = args.set_extra
    meta = {}
    if args.discipline: meta["学科"] = args.discipline
    if args.research_type: meta["研究类型"] = args.research_type
    if not updates and not meta: raise ValueError("update至少需要提供一个要修改的字段")
    with mutation_lock(Path(args.db)):
        cards = load(Path(args.db))
        card = next((c for c in cards if c["id"] == args.id), None)
        if card is None: raise ValueError(f"未找到卡片：{args.id}")
        before = dict(card)
        append = updates.pop("_append_tags", None)
        set_extra = updates.pop("_set_extra", None)
        card.update(updates)
        if append:
            card["标签"] = ", ".join(dict.fromkeys(tags(card.get("标签","")) + tags(append)))
        if set_extra:
            card[EXTRA] = parse_extra(set_extra, card.get(EXTRA))
        if meta:
            extra = dict(card.get(EXTRA) or {}); extra.update(meta); card[EXTRA] = extra
        card["标签"] = ", ".join(tags(card.get("标签","")))
        if not card.get("title", "").strip():
            card.clear(); card.update(before)
            raise ValueError("标题不能为空")
        if "风险" in updates:
            try:
                check_risk(card)
            except ValueError as exc:
                card.clear(); card.update(before)
                raise ValueError(str(exc)) from None
        if meta:
            try:
                check_meta(card)
            except ValueError as exc:
                card.clear(); card.update(before)
                raise ValueError(str(exc)) from None
        duplicate = next((c for c in cards if c is not card and content_key(c) == content_key(card)), None)
        if duplicate and not args.allow_duplicate:
            card.clear(); card.update(before)
            raise ValueError(f"修改后与{duplicate['id']}重复；若确需保留副本，请使用--allow-duplicate")
        card["updated"] = stamp()
        save(Path(args.db), cards)
    print(f"[已更新] {card['id']}  {card['title']}")

def delete_card(args) -> None:
    if not args.yes: raise ValueError("删除会移除卡片；确认后请追加--yes。删除前会保留.bak备份")
    with mutation_lock(Path(args.db)):
        cards = load(Path(args.db))
        kept = [c for c in cards if c["id"] != args.id]
        if len(kept) == len(cards): raise ValueError(f"未找到卡片：{args.id}")
        save(Path(args.db), kept)
    print(f"[已删除] {args.id}；删除前数据库保存在{args.db}.bak")

def show_cards(cards: list[dict]) -> None:
    for c in cards:
        print(f"{c['id']} [{c.get('风险') or '未评级'}] {c['title']}")
        for field in FIELDS:
            print(f"  {field}: {c.get(field) or '—'}")
        for key, value in (c.get(EXTRA) or {}).items():
            print(f"  {key}: {value}")
        print()

def command_list(args) -> None:
    cards = load(Path(args.db))
    if args.tag:
        wanted = set(tags(args.tag)); cards = [c for c in cards if wanted & set(tags(c.get("标签","")))]
    research = getattr(args, "research_type", None)
    if research:
        research = research.strip()
        if research not in RESEARCH_TYPES:
            raise ValueError(f"研究类型必须为：{'、'.join(sorted(RESEARCH_TYPES))}（当前值：{research}）")
        cards = [c for c in cards if (c.get(EXTRA) or {}).get("研究类型") == research]
    if cards: show_cards(cards)
    else: print("（没有匹配的卡片）")

def command_search(args) -> None:
    keyword = args.keyword.strip()
    if not keyword: raise ValueError("搜索词不能为空；查看全部卡片请使用list")
    cards = load(Path(args.db)); needle = keyword.casefold()
    hits = [c for c in cards if needle in haystack(c)]
    if hits: show_cards(hits)
    else: print(f"未找到包含“{keyword}”的卡片")

def command_show(args) -> None:
    cards = load(Path(args.db)); card = next((c for c in cards if c["id"] == args.id or c["title"] == args.id), None)
    if card is None: raise ValueError(f"未找到卡片：{args.id}")
    show_cards([card])

def command_combine(args) -> None:
    cards = load(Path(args.db)); a_tags, b_tags = set(tags(args.tag)), set(tags(args.tag2))
    group_a = [c for c in cards if a_tags & set(tags(c.get("标签","")))]
    group_b = [c for c in cards if b_tags & set(tags(c.get("标签","")))]
    pairs = []
    seen = set()
    for a in group_a:
        for b in group_b:
            if a["id"] == b["id"] or content_key(a) == content_key(b): continue
            pair = tuple(sorted((a["id"], b["id"])))
            if pair not in seen: seen.add(pair); pairs.append((a,b))
    if not pairs:
        raise ValueError(f"没有可组合的不同卡片（{len(group_a)}张与{len(group_b)}张命中，已排除自组合）")
    print(f"# 交叉组合：{args.tag} × {args.tag2}（{len(pairs)}对）")
    for a,b in pairs:
        print(f"\n## {a['id']} × {b['id']}")
        print(f"- A标题：{a['title']}")
        print(f"- A短板：{a.get('短板') or '待补充'}")
        print(f"- B标题：{b['title']}")
        print(f"- B短板：{b.get('短板') or '待补充'}")
        print("- 组合问题：两项限制会不会在同一场景同时发生？")
        print("- 待验证：说明合并后机制、差异及可推翻实验。")

def command_stats(args) -> None:
    cards = load(Path(args.db))
    if not cards: print("（素材库为空）"); return
    tag_counts = {}
    gap_counts = {}
    for c in cards:
        for tag in tags(c.get("标签","")): tag_counts[tag] = tag_counts.get(tag,0)+1
        gap = c.get("短板","").strip()
        if gap: gap_counts[gap] = gap_counts.get(gap,0)+1
    print(f"卡片总数：{len(cards)}")
    discipline_counts = {}
    for c in cards:
        name = (c.get(EXTRA) or {}).get("学科")
        if name: discipline_counts[name] = discipline_counts.get(name, 0) + 1
    if discipline_counts:
        print("按学科：")
        for name, n in sorted(discipline_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {name}：{n}")
    type_counts = {}
    for c in cards:
        name = (c.get(EXTRA) or {}).get("研究类型")
        if name: type_counts[name] = type_counts.get(name, 0) + 1
    if type_counts:
        print("按研究类型：")
        for name, n in sorted(type_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {name}：{n}")
    fingerprints={}
    for c in cards: fingerprints.setdefault(content_key(c), []).append(c["id"])
    duplicates=[ids for ids in fingerprints.values() if len(ids)>1]
    if duplicates: print("完全重复内容（计数保留原始卡片；请人工合并）：" + "; ".join(", ".join(ids) for ids in duplicates))
    print("按标签：")
    for tag,n in sorted(tag_counts.items(), key=lambda item:(-item[1],item[0])): print(f"  {tag}：{n}")
    repeated = [(g,n) for g,n in gap_counts.items() if n>=2]
    if repeated:
        print("重复短板（按文本完全匹配）：")
        for gap,n in sorted(repeated,key=lambda item:(-item[1],item[0])): print(f"  {gap}：{n}")

def command_template(args) -> None:
    sys.stdout.write(TEMPLATE)

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="科研idea素材库（带并发锁和原子保存）")
    p.add_argument("--db",default=str(DEFAULT_DB),help="卡片JSON路径；建议在授权的工作目录中显式指定")
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("add",help="新增单张卡片")
    a.add_argument("--file");a.add_argument("--title");a.add_argument("--source");a.add_argument("--problem");a.add_argument("--current");a.add_argument("--gap");a.add_argument("--extend");a.add_argument("--oneline");a.add_argument("--risk",choices=sorted(RISK_VALUES));a.add_argument("--validation");a.add_argument("--tags");a.add_argument("--tag");a.add_argument("--set-extra",action="append",metavar="KEY=VALUE",help="自定义字段，可重复");a.add_argument("--discipline",metavar="学科",help="学科，写入扩展字段");a.add_argument("--research-type",dest="research_type",metavar="类型",help="研究类型，写入扩展字段");a.add_argument("--allow-duplicate",action="store_true")
    a.set_defaults(func=add_card)
    u=sub.add_parser("update",help="按ID更新卡片");u.add_argument("id")
    u.add_argument("--title");u.add_argument("--source");u.add_argument("--problem");u.add_argument("--current");u.add_argument("--gap");u.add_argument("--extend");u.add_argument("--oneline");u.add_argument("--risk",choices=sorted(RISK_VALUES));u.add_argument("--validation");u.add_argument("--tags");u.add_argument("--tag");u.add_argument("--set-extra",action="append",metavar="KEY=VALUE",help="自定义字段，可重复");u.add_argument("--discipline",metavar="学科",help="学科，写入扩展字段");u.add_argument("--research-type",dest="research_type",metavar="类型",help="研究类型，写入扩展字段")
    u.add_argument("--allow-duplicate",action="store_true");u.set_defaults(func=update_card)
    d=sub.add_parser("delete",help="按ID删除卡片，要求显式--yes并生成备份");d.add_argument("id");d.add_argument("--yes",action="store_true");d.set_defaults(func=delete_card)
    l=sub.add_parser("list",help="列出卡片");l.add_argument("--tag");l.add_argument("--research-type",dest="research_type",metavar="类型",help="按研究类型筛选");l.set_defaults(func=command_list)
    s=sub.add_parser("search",help="按卡片字段全文检索");s.add_argument("keyword");s.set_defaults(func=command_search)
    sh=sub.add_parser("show",help="按ID或标题查看");sh.add_argument("id");sh.set_defaults(func=command_show)
    c=sub.add_parser("combine",help="配对两组标签卡片供研究者继续判断");c.add_argument("--tag",required=True);c.add_argument("--tag2",required=True);c.set_defaults(func=command_combine)
    st=sub.add_parser("stats",help="统计标签和完全相同短板");st.set_defaults(func=command_stats)
    t=sub.add_parser("template",help="打印单卡Markdown模板");t.set_defaults(func=command_template)
    return p

def main() -> int:
    p=parser();args=p.parse_args()
    try:
        args.func(args);return 0
    except (OSError,UnicodeError,ValueError,TimeoutError) as exc:
        print(f"[错误] {exc}",file=sys.stderr);return 2

if __name__=="__main__":
    raise SystemExit(main())
