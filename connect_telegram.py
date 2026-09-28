#!/usr/bin/env python3
"""Saved sealed-card consumer: key on stdin, never in args, output or logs."""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request
from bridge_setup import connect


def api(path,body=None,method=None):
    if not os.environ.get('CHAT_ID') or os.environ.get('APP_TOKEN'):
        raise ValueError('Sealed owner context required')
    bearer=(Path(os.environ.get('DATA_DIR','/data'))/'service-token.txt').read_text().strip()
    request=urllib.request.Request(os.environ['API_BASE_URL'].rstrip('/')+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+bearer,'Content-Type':'application/json'},
        method=method or ('POST' if body is not None else 'GET'))
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read();return json.loads(raw) if raw else {}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app-id',type=int,required=True)
    parser.add_argument('--api-base',required=True);args=parser.parse_args()
    if not os.environ.get('CHAT_ID') or os.environ.get('APP_TOKEN'):raise ValueError()
    os.environ['API_BASE_URL']=args.api_base
    fields=json.load(sys.stdin)
    try:connect({'fields':fields},api,args.app_id)
    finally:fields.clear()


if __name__=='__main__':
    try:main()
    except Exception:sys.exit(1)
