"""Public saved-card prompt identity; no submitted value or secret stored here."""
import json
from uuid import NAMESPACE_URL,uuid5
TITLE='Connect your personal Telegram Bridge'
DESCRIPTION=('Verify this dedicated bot with Telegram and encrypt its key for this Bridge. '
 'No listening, message or pairing change. A different bot needs another reviewed installation. '
 'Never paste the key into chat.')
FIELDS=[{'name':'bot_token','type':'password','label':'Telegram bot key','autocomplete':'off'}]


def request_identity(chat_id,owner_run,command,cwd):
 card={'questions':[{'id':'secure_input','header':'Secure input','question':TITLE,'options':[]}],
  'secure_input':{'title':TITLE,'description':DESCRIPTION,'mode':'sealed','fields':FIELDS}}
 spec={'command':list(command),'cwd':cwd,'action':'run'}
 # Public save_owner_question's immutable id binds to the actual authoring run.
 # A guest/delegated run cannot substitute an older owner run through an argv.
 return str(uuid5(NAMESPACE_URL,json.dumps([chat_id,owner_run,{'card':card,'consumer':spec}],sort_keys=True)))
