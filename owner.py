#!/usr/bin/env python3
"""Owner-chat helper: save one existing sealed-input pause, no values received."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from trusted_setup import installed_context
from telegram_http import safe_origin
from setup_spec import TITLE,DESCRIPTION


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['connect']);p.add_argument('--app-id',type=int,required=True);args=p.parse_args()
 context=installed_context(args.app_id,owner_prepare=True)
 base=safe_origin(os.environ['API_BASE_URL'].rstrip('/'))
 command=[sys.executable,str(Path(context['root'])/'connect_telegram.py'),'--app-id',str(args.app_id),
  '--nonce',context['nonce'],'--revision',context['revision'],'--api-base',base,'--owner-run',context['owner_run']]
 # The real owner chat's existing saved secure-input route is the sole UI.
 # No ordinary input, pasted instruction, APP_OWNER_ACTION or owner token file.
 saved=[sys.executable,'/data/platform/backend/scripts/secure-input.py','run',
  '--title',TITLE,'--description',DESCRIPTION,
  '--field','bot_token:password:Telegram bot key','--',*command]
 return subprocess.run(saved,cwd=context['root']).returncode

if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception:
  print('Secure setup was not saved. Run this helper from the accepted Bridge source in a nondelegated owner chat.',file=sys.stderr)
  raise SystemExit(1)
