"""Bridge setup and companion access approvals; no owner-chat grants."""
import json
import os
import sys





def dispatch(request):
    if request.get('path','').strip('/') == 'bot-info':
        actor=request.get('actor') or {}
        if (request.get('method')!='GET' or request.get('public') or actor.get('delegated')
            or actor.get('scope') not in ('owner','app')
            or (actor.get('scope')=='app' and actor.get('app_id')!=int(os.environ['APP_ID']))):
            raise ValueError('Own management screen only')
        from telegram_http import call_saved,bot_identity
        return bot_identity(call_saved('bot-token','getMe',app_id=os.environ['APP_ID'],
            bearer=os.environ['APP_TOKEN'],api_base=os.environ['API_BASE_URL']))
    from bridge_access import binding
    return binding(request)

if __name__=='__main__':
    try:
        print(json.dumps({'body':dispatch(json.load(sys.stdin)),'headers':{'Cache-Control':'no-store'}}))
    except Exception:
        print(json.dumps({'status':403,'body':{'error':'Bridge management unavailable.'}}))
