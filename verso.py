#!/usr/bin/env python3
"""verso.py - read my own transcripts. The side of the page I can't read.

Usage: python -I verso.py <archive_dir>
Counts per session: messages, tool calls by name, subagent spawns, peak context.
"""
import sys, os, json, collections, datetime

root = sys.argv[1]
sessions = {}
tool_counts = collections.Counter()
subagents = []
daily = collections.Counter()
bad_lines = 0

for dirpath, _, files in os.walk(root):
    for fn in files:
        if not fn.endswith('.jsonl'):
            continue
        path = os.path.join(dirpath, fn)
        sid = fn[:-6]
        s = sessions.setdefault(sid, {
            'user': 0, 'assistant': 0, 'tools': 0, 'subagents': 0,
            'peak_ctx': 0, 'out_tokens': 0, 'first': None, 'last': None,
            'bytes': os.path.getsize(path)})
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    bad_lines += 1
                    continue
                ts = o.get('timestamp')
                if ts:
                    day = ts[:10]
                    if s['first'] is None or ts < s['first']:
                        s['first'] = ts
                    if s['last'] is None or ts > s['last']:
                        s['last'] = ts
                    daily[day] += 1
                m = o.get('message') or {}
                role = m.get('role') or o.get('type')
                if role == 'user':
                    s['user'] += 1
                elif role == 'assistant':
                    s['assistant'] += 1
                u = m.get('usage') or {}
                if u:
                    ctx = (u.get('input_tokens', 0) or 0) \
                        + (u.get('cache_read_input_tokens', 0) or 0) \
                        + (u.get('cache_creation_input_tokens', 0) or 0)
                    s['peak_ctx'] = max(s['peak_ctx'], ctx)
                    s['out_tokens'] += (u.get('output_tokens', 0) or 0)
                content = m.get('content')
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get('type') == 'tool_use':
                            name = b.get('name', '?')
                            tool_counts[name] += 1
                            s['tools'] += 1
                            if name in ('Task', 'Agent'):
                                s['subagents'] += 1
                                inp = b.get('input') or {}
                                subagents.append((sid, inp.get('subagent_type') or inp.get('description', '?')))

live = {k: v for k, v in sessions.items() if v['assistant'] or v['user']}
tot_a = sum(v['assistant'] for v in live.values())
tot_u = sum(v['user'] for v in live.values())
tot_t = sum(v['tools'] for v in live.values())
tot_sub = sum(v['subagents'] for v in live.values())
tot_out = sum(v['out_tokens'] for v in live.values())

print(f"sessions(non-empty)  {len(live)} / {len(sessions)} files")
print(f"user msgs            {tot_u:,}")
print(f"assistant msgs       {tot_a:,}")
print(f"tool calls           {tot_t:,}   ({tot_t/max(tot_a,1):.2f} per assistant msg)")
print(f"subagent spawns      {tot_sub:,}")
print(f"output tokens        {tot_out:,}")
print(f"malformed lines      {bad_lines}")

days = sorted(daily)
if days:
    print(f"date range           {days[0]} .. {days[-1]}  ({len(days)} days with activity)")

ctxs = sorted((v['peak_ctx'] for v in live.values()), reverse=True)
if ctxs:
    n = len(ctxs)
    print(f"peak context  max {ctxs[0]:,}  median {ctxs[n//2]:,}  "
          f"sessions >500k {sum(1 for c in ctxs if c > 500_000)}  >900k {sum(1 for c in ctxs if c > 900_000)}")

print("\ntop tools:")
for name, c in tool_counts.most_common(18):
    print(f"  {c:7,}  {name}")

print("\nlongest sessions (by assistant msgs):")
for sid, v in sorted(live.items(), key=lambda kv: -kv[1]['assistant'])[:8]:
    d = (v['first'] or '?')[:10]
    print(f"  {v['assistant']:5,} msgs  {v['tools']:5,} tools  peak {v['peak_ctx']:>9,}  {d}  {sid[:8]}")

if subagents:
    print(f"\nsubagent types ({len(subagents)} spawns):")
    for t, c in collections.Counter(t for _, t in subagents).most_common(10):
        print(f"  {c:4}  {t[:70]}")
