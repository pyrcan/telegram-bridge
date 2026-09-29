# Telegram Bridge

Your personal Möbius owner agent in a paired private Telegram chat. Telegram
transport and conversation handling live in this app, not a platform Telegram proxy.

> **Platform requirement:** use Möbius with the supervised-job secret permission
> added in [PR #1565](https://github.com/mobius-os/mobius/pull/1565). It is included
> in official image revision `928fef19ebabc7023375a748f0c8718831cb5605`
> (published 29 September 2026), or a later compatible revision. Update Möbius
> before connecting a bot; older versions cannot run these jobs.
> No Telegram proxy, new confirmation system or service-concurrency change is required.

## Two companion apps

- **Telegram Bridge** works on its own: pair one private Telegram account, create
  app-owned conversations, choose models and answer saved Möbius questions.
- **Telegram Bot Studio** is a separate app for building, privately testing and
  publishing specialist bots. **Pair Bridge first**, then connect a different bot
  in Studio. Studio uses the pairing to verify the owner's Telegram identity.
- Specialist participants never receive the owner agent. Their notes and
  conversations stay separate. Installation alone grants no cross-app access.

Catalog navigation is a separately approved metadata-only connection. User
management alone lists only the published bots covered by that narrower grant. Optional
**Enable user management** covers access requests and alerts for current and
future published Studio bots owned by the paired account. It does not expose
participant content or authorize publication, bot activation or model changes.
Customization opens in Möbius; continuing pre-existing owner chats from Telegram
and direct whole-shell screenshot shortcuts are not included in this Store edition.

Studio's display name was formerly Assistant Studio. Its `assistant-studio`
package/service identity is stable; app names and source folder names are not IDs.

## Setup

1. Create a dedicated bot in BotFather, not one already connected to another app.
2. Choose **Connect securely** and send the prepared request in Möbius chat. Enter
   the key only in that chat's sealed card, never as a chat message. The consumer
   verifies the bot, refuses an existing webhook, encrypts the key and starts
   listening if Bridge is enabled. It never removes a webhook automatically.
3. Send the displayed pairing command from your private Telegram account. The
   first valid private account is paired; other accounts cannot use your agent.
4. In **Settings → Möbius address**, save the installation's HTTPS origin without
   paths, credentials or query parameters. It is used only in navigation buttons,
   never for credentialed requests. Blank disables links, not text replies.

Generated images stay in the authenticated Möbius conversation. Telegram receives
text plus **Open in Möbius**, without media-access keys. A normal sign-in is still
required. Neither image files nor owner credentials are sent with those links.

## Using Bridge

Telegram's native menu offers Chats, My bots, Settings and Help. `/new` creates a
fresh Bridge-owned conversation. `/model` changes the model for new conversations;
`/status` shows connection state. Routine replies have no navigation footer.
Saved questions use compact buttons and typed alternatives; stale controls retire
when answered in Möbius. UI-only or unsupported cards link back to Möbius.

Model replies use your owner agent and may incur usage. Menu navigation does not
call a model. Pausing retains pending work; revoking pairing stops future access.
In-flight external requests can finish. A fresh pairing never grants access to
pre-existing owner chats or specialist participant content.

## Runtime and privacy

The existing supervised app job owns polling and bounded worker lanes. Intake is
saved before the Telegram cursor advances. One ordered worker handles conversation
mutations while read-only controls and acknowledgements remain responsive. App-owned
locks protect shared status/connection writes. Platform service limits stay unchanged.

Message submission has an update-derived idempotency key. Telegram sends do not:
a crash after delivery can still repeat a Bridge reply. Do not claim exactly-once
external delivery. Cosmetic response drafts contain public reply text, not reasoning
or tool results; failure never prevents the final response.

The job may read only its declared `bot-token` from the encrypted own-app secret
store. The browser receives no key or raw Telegram response. Keys are not cached
between calls. A compromised approved job could leak its permitted key; revocation
cannot retract one already read. Trusted app code is not an OS sandbox.

Studio access management uses live pairing/grant checks and exact-user state reviews.
Disconnect keeps users' existing access/content but stops future delegated management.
Notification receipts fence uncertain sends; the Users list is the recovery path.
No notes, conversations, sessions, models or billing are exposed by that grant.

## Owner chat setup and confirmations

Sensitive app buttons prepare editable Möbius chat requests. The owner sends
them; clicking a button is not approval and never sends a model turn. Treat the
JSON selection as data. Resolve the numeric app ID and service identity first.

For key setup/replacement, run `python3 <source_dir>/owner.py connect --app-id <id>`
as the turn's final action. It opens the existing sealed-input card. The card
explains that a dedicated bot is verified, the key encrypted, the paired account
retained and the normal listener started if enabled. The key never enters the
chat transcript, model, app frame or action arguments. Do not execute the sealed
consumer yourself or ask for keys in chat.

For connect-access/disconnect-access, inspect the current pairing and grant.
Explain that connection covers user access and request alerts for current AND
future Studio bots owned by the paired account, but no participant content.
Allowing users can send notices and incur usage. Disconnection keeps existing
user access unchanged; in-flight operations may finish. Obtain one exact saved
approval with pairing user/chat/date or the current grant. After approval only,
pass the reviewed `{ "action": "connect-access", "context": {...} }` (or
disconnect-access) on stdin to `python3 <source_dir>/owner.py execute --app-id <id>`.
The helper checks the live pairing and serializes mapping changes. Changed state
requires a new review, not silently replacing the approved selection. Decline
changes nothing. Jobs and app frames cannot use this owner helper.

## Verification and license

Run `python3 -m pytest -q` from this repository. Tests use synthetic data and fake
Telegram/Möbius responses, not live messages or paid model calls. See
[TESTING.md](TESTING.md) for isolated browser fixtures. Never run those fixtures
against an installed app. Native Telegram client behavior needs separate testing.

MIT; see [LICENSE](LICENSE). Runtime UI dependencies come from Möbius, not vendored
archives. Telegram is a third-party service; this is not an official Telegram
product. Store screenshots use synthetic data. No keys, runtime state or private
chat history are included in this source-only package.

### Optional catalog navigation

To list draft/setup metadata and editing-chat links in Bridge, request a separate
saved approval naming the exact installed Bridge app ID and this metadata-only
scope. In an owner chat, call Studio's owner helper with
`call('owner/navigation', {'app_id': <reviewed-Bridge-id>})` only after approval.
This is not needed for the narrower published-bot user-management list. No
participant data, chat transcript, activation or publication authority is shared.
