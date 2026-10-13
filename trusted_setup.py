"""Only the saved sealed owner-chat consumer uses platform-side primitives.

Never import this in the frame, listener or app service. No owner bearer is
minted or read from a credential file. Preparation validates the actual current
owner-chat bearer; the sealed consumer receives none. Current app nonce, accepted runtime and exact consuming card fence
one short-lived ordinary own-app credential; no service/job/owner claims.
"""
import os
from pathlib import Path
import sys
from datetime import timedelta
from setup_spec import request_identity


def platform():
 # Public deployed helper/import path; not a copy of platform code.
 sys.path.insert(0,'/data/platform/backend')
 from app import auth,models
 from app.database import SessionLocal
 from app.applied_app_runtime import runtime_parent
 return auth,models,SessionLocal,runtime_parent


def installed_context(app_id, *, owner_prepare=False, expected_nonce=None, expected_revision=None, command=None, owner_run=None):
 if os.environ.get('APP_TOKEN') or not os.environ.get('CHAT_ID'):raise ValueError('Trusted owner chat required')
 auth,models,SessionLocal,runtime_parent=platform()
 with SessionLocal() as db:
  app=db.query(models.App).filter(models.App.id==app_id,models.App.deleted_at.is_(None)).first()
  owner=db.query(models.Owner).first()
  chat=db.query(models.Chat).filter(models.Chat.id==os.environ['CHAT_ID'],models.Chat.deleted_at.is_(None)).first()
  if not app or not owner or not chat:raise ValueError('Current installation required')
  root=runtime_parent(app.id)/str(app.runtime_revision)
  if not app.runtime_revision or not root.is_dir() or Path(__file__).resolve().parent!=root.resolve():raise ValueError('Run only accepted setup source')
  contract=app.capability_contract or {}
  if contract.get('data',{}).get('job_secret_read')!=['bot-token']:raise ValueError('Reviewed named-key grant required')
  if app.slug!='telegram-bridge':raise ValueError('Matching Bridge identity required')
  if owner_prepare:
   from app.deps import get_agent_run_principal,require_installation_owner_control
   principal=get_agent_run_principal(os.environ.get('AGENT_TOKEN') or '',db)
   require_installation_owner_control(principal)
   if principal.chat_id!=chat.id or principal.owner.id!=owner.id:raise ValueError('Current installation owner run required')
   return {'nonce':app.token_nonce,'revision':app.runtime_revision,'root':str(root),'owner_run':principal.run_id}
  if os.environ.get('AGENT_TOKEN') or expected_nonce!=app.token_nonce or expected_revision!=app.runtime_revision:raise ValueError('Setup installation changed')
  origin=db.query(models.ChatRun).filter(models.ChatRun.id==owner_run,models.ChatRun.chat_id==chat.id).first()
  if not origin or origin.browser_grant_id is not None:raise ValueError('Saved input was not authored by the installation owner')
  if db.query(models.Delegation).filter(models.Delegation.child_chat_id==chat.id).first():raise ValueError('Delegated consumers are unavailable')
  exact_id=request_identity(chat.id,owner_run,command,str(root))
  cards=db.query(models.SavedSecureInput).filter_by(chat_id=chat.id,status='consuming',action='run').all()
  if not any(c.request_id==chat.pending_question_id==exact_id and c.command_json==command and Path(c.cwd).resolve()==root.resolve() for c in cards):raise ValueError('Exact consuming sealed card required')
  # No service/job_secrets argument, never an owner credential. The sealed consumer can
  # touch only this app through existing API guards, for two minutes at most.
  bearer=auth.create_app_token(app.id,owner.username,owner.token_epoch,app_nonce=app.token_nonce,expires_delta=timedelta(minutes=2))
  return {'bearer':bearer,'root':str(root)}
