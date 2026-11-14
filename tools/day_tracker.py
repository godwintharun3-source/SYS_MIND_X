#!/usr/bin/env python3
"""Human-reviewed tracker for the SYSTEM MIND 365-day Antigravity plan."""
from pathlib import Path
import argparse, json
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.project-state'/'current_day.json'
LOG=ROOT/'docs'/'DAILY_LOG.md'
def read_state(): return json.loads(STATE.read_text(encoding='utf-8'))
def write_state(s):
    s['last_updated']=datetime.now().astimezone().isoformat(timespec='seconds')
    STATE.write_text(json.dumps(s,indent=2),encoding='utf-8')
def main():
    p=argparse.ArgumentParser(description='Track reviewed SYSTEM MIND development days')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('status')
    st=sub.add_parser('start'); st.add_argument('--day',type=int,required=True)
    co=sub.add_parser('complete'); co.add_argument('--day',type=int,required=True); co.add_argument('--summary',required=True); co.add_argument('--tests',required=True); co.add_argument('--reviewed',action='store_true',help='Required acknowledgement that a human reviewed the diff and evidence')
    a=p.parse_args(); s=read_state()
    if a.cmd=='status':
        print(json.dumps(s,indent=2))
        if s.get('status') == 'v1_0_review_complete':
            print('All 365 workdays are marked reviewed complete.')
        else:
            print(f"Next prompt: daily-prompts/DAY-{s['current_day']:03d}.md")
        return
    if a.day != s['current_day']:
        raise SystemExit(f"Refusing: current day is {s['current_day']}, requested {a.day}. Do not skip or replay a different day.")
    if a.cmd=='start':
        if s['status']=='awaiting_review': raise SystemExit('This day is awaiting human review. Review it or keep working; do not restart it.')
        s['status']='in_progress'; s['started_on']=s.get('started_on') or datetime.now().astimezone().isoformat(timespec='seconds'); write_state(s)
        print(f"Day {a.day:03d} started. Prompt: daily-prompts/DAY-{a.day:03d}.md")
    elif a.cmd=='complete':
        if not a.reviewed: raise SystemExit('Refusing: pass --reviewed only after a human has inspected the diff and test evidence.')
        if not a.summary.strip() or not a.tests.strip(): raise SystemExit('Summary and test evidence must be non-empty.')
        s['last_reviewed_completed_day']=a.day
        s['current_day']=a.day+1 if a.day<365 else 366
        s['status']='not_started' if a.day<365 else 'v1_0_review_complete'
        s['active_phase']='See docs/ROADMAP_365_DAYS.md'
        write_state(s)
        with LOG.open('a',encoding='utf-8') as f:
            f.write(f"\n## Day {a.day:03d} - Human reviewed complete\n\n- Reviewed summary: {a.summary}\n- Test evidence: {a.tests}\n- Review timestamp: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
        print(f"Day {a.day:03d} marked reviewed. Next day: {s['current_day']:03d}")
if __name__=='__main__': main()
