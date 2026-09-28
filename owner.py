#!/usr/bin/env python3
"""Owner chat helper. Sensitive actions require the chat's saved approval first."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request


def api(path, body=None, method=None):
    if os.environ.get('APP_TOKEN') or not os.environ.get('AGENT_TOKEN'):
        raise ValueError('Owner chat required')
    request=urllib.request.Request(os.environ['API_BASE_URL'].rstrip('/')+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+os.environ['AGENT_TOKEN'],'Content-Type':'application/json'},
        method=method or ('POST' if body is not None else 'GET'))
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read();return json.loads(raw) if raw else {}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['connect','execute']);p.add_argument('--app-id',type=int,required=True)
    args=p.parse_args()
    if os.environ.get('APP_TOKEN') or not os.environ.get('AGENT_TOKEN'):
        raise ValueError('Owner chat required')
    app=api(f'/api/apps/{args.app_id}')
    if (app.get('capability_contract') or {}).get('service',{}).get('id')!='telegram-bridge':
        raise ValueError('Select the installed Telegram Bridge')
    if args.action=='connect':
        command=[sys.executable,'/data/platform/backend/scripts/secure-input.py','run',
            '--title','Connect your personal Telegram Bridge',
            '--description','Verify and encrypt this dedicated bot key. Replacement keeps your paired account. Start listening if enabled; your paired owner agent may incur usage. Use a bot not running elsewhere.',
            '--field','bot_token:password:Telegram bot key','--',sys.executable,
            str(Path(__file__).with_name('connect_telegram.py')),'--app-id',str(args.app_id),
            '--api-base',os.environ['API_BASE_URL']]
        raise SystemExit(subprocess.run(command).returncode)
    from bridge_access import owner_action
    os.environ['APP_ID']=str(args.app_id)
    os.environ['APP_STORAGE_DIR']=str(Path(os.environ.get('DATA_DIR','/data'))/'apps'/str(args.app_id))
    owner_action(json.load(sys.stdin),api)
    print('Completed. Check the current connection before any retry.')


if __name__=='__main__':
    try:main()
    except Exception:
        print('Bridge action did not finish. Check current state before retrying.',file=sys.stderr)
        sys.exit(1)
