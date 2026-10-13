#!/usr/bin/env python3
"""Pre-authored sealed consumer: stdin → dedicated-bot check → encrypted app key."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request
from telegram_http import KEY,NoRedirect,call_key,safe_origin
from trusted_setup import installed_context


def connect(fields,app_id,api,inspect=call_key):
 key=fields.get('bot_token')
 if not isinstance(key,str) or not KEY.fullmatch(key):raise ValueError('Invalid key')
 bot=inspect(key,'getMe');hook=inspect(key,'getWebhookInfo')
 if not isinstance(hook,dict) or hook.get('url'):raise ValueError('Dedicated bot without webhook required')
 old=api('GET','bot-identity')
 if old and old.get('id')!=bot['id']:raise ValueError('This installation is bound to another bot')
 api('PUT','bot-token',{'value':key})
 api('PUT','bot-identity',{'id':bot['id'],'username':bot['username']})


def local_api_origin(requested):
 expected=safe_origin(os.environ.get('API_BASE_URL','').rstrip('/'))
 if requested!=expected:raise ValueError('Use only the configured local app API origin')
 return expected


def main():
 p=argparse.ArgumentParser();p.add_argument('--app-id',type=int,required=True);p.add_argument('--nonce',required=True);p.add_argument('--revision',required=True);p.add_argument('--api-base',required=True);p.add_argument('--owner-run',required=True)
 args=p.parse_args()
 ctx=installed_context(args.app_id,expected_nonce=args.nonce,expected_revision=args.revision,owner_run=args.owner_run,command=[sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]])
 base=local_api_origin(args.api_base)
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 def api(method,name,body=None):
  current=installed_context(args.app_id,expected_nonce=args.nonce,expected_revision=args.revision,owner_run=args.owner_run,command=[sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]])
  if name=='bot-token' and method=='PUT':path=f'/api/apps/{args.app_id}/secrets/bot-token'
  elif name=='bot-identity' and method in ('GET','PUT'):path=f'/api/storage/apps/{args.app_id}/bot-identity.json'
  else:raise ValueError()
  req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
   headers={'Authorization':'Bearer '+current['bearer'],'Content-Type':'application/json'},method=method)
  try:
   with opener.open(req,timeout=15) as response:
    raw=response.read(8193)
    if len(raw)>8192:raise ValueError()
    return json.loads(raw) if raw else None
  except urllib.error.HTTPError as exc:
   if method=='GET' and exc.code==404:return None
   raise ValueError('Setup could not be confirmed') from None
 fields={}
 try:
  raw=sys.stdin.read(8193)
  if len(raw)>8192:raise ValueError()
  fields=json.loads(raw)
  if not isinstance(fields,dict) or set(fields)!={'bot_token'}:raise ValueError()
  connect(fields,args.app_id,api)
 finally:
  fields.clear();ctx.clear();raw=None

if __name__=='__main__':
 try:main()
 except Exception:raise SystemExit(1)
