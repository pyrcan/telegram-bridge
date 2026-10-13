# Telegram Bridge · public-core edition

A dedicated private Telegram bot is your owner remote for **Bridge-created**
Möbius conversations. Chats, Bots and Tools retain the current Bridge visual
language. This edition uses supported public core contracts at
`9ebca6c8584400e6adc419ee8196a0fb82d19896`; no core patch is required.
Review COMPATIBILITY.md before upgrading another edition: unsupported features are not migrated.

## Secure first-time setup

1. Create a dedicated bot with BotFather. Do not reuse a running specialist bot
   or a bot with a webhook. Installation grants nothing in Studio.
2. Settings → **Set up securely in Möbius** opens an editable owner-chat draft,
   not an action, approval, credential input or transcript transfer. Send it in
   your ordinary nondelegated owner chat if you want to connect.
3. The owner agent resolves this numeric app's accepted `job-context.runtime_dir`
   and runs its accepted `owner.py connect --app-id <id>` with the platform
   Python environment. The helper verifies current app identity/nonce/runtime
   and saves the public existing sealed-input form **as the final turn action**.
   End that owner-chat turn on its saved receipt, without more text/tools.
   Do not run this helper from editable source, a job, a service or a child chat.
4. Enter the BotFather key only into that saved trusted form. Its narrow consumer
   verifies `getMe` and `getWebhookInfo`, encrypts the key via this app's secret
   API, and records only safe bot identity metadata. It never starts a job,
   changes pairing, clears a webhook or sends a message. An existing installation
   cannot silently switch to a different bot. No token is printed, logged,
   copied into arguments/environment, or shown to the app frame/model.
5. Prepare the one-time pairing code in Settings, then explicitly **Enable
   listening**. The supervisor/cron owns one listener. Send the visible pairing
   command to your personal bot. Only the first matching private account is
   paired; its code is consumed. Other accounts/groups are ignored. A paired
   owner's ordinary text can incur configured provider usage.

The consumer is tied to the exact saved card in `consuming` state, its canonical
public request identity and non-guest/nondelegated originating owner run, its current
chat, accepted runtime, app nonce and reviewed `job_secret_read: [bot-token]`
contract. It mints only a two-minute **ordinary own-app** credential
through existing public auth primitives, with no owner, service or job claims. No general
owner token file is used. Submitted values only enter the intended Telegram API
check and encrypted app-secret destination. Setup runs only after you submit the sealed owner form.

## Use

- Send ordinary text for a reply. `/menu`, `/chats`, `/new`, `/model`, `/status`,
  `/bots`, and `/bridge` provide native navigation. Read menus remain responsive
  while ordered owner work runs. Message batches persist before receive-cursor
  advancement. Model changes create a new chat; old conversations stay saved.
- `/chats` reads only fresh Bridge-owned metadata. Review a conversation and
  explicitly **Continue here** to route the next message. Opening it in Möbius
  does not change the Telegram destination. Archive state is not publicly
  exposed, so this edition never labels the list Active/Archived.
- Exact ordinary saved cards preserve canonical question/option IDs, prompt
  strings and labels. Oversized, unsupported, secure-input and typed platform
  cards link to Möbius. Telegram answers are **agent-scoped input**, never proof
  of trusted owner approval. Sensitive authority remains in Möbius.
- Optional Studio metadata is read only through its already-authorized service,
  checked against `owner-metadata-v1`, fresh numeric app identity and accepted runtime metadata.
  Missing/restricted/mismatched Studio does not impair personal Bridge. Bot
  navigation does not install, connect, activate, publish or grant chat access.
- Pause stops future intake; already accepted work or in-flight delivery may
  finish. Revocation/replacement needs explicit owner-chat review. No pairing,
  key, grant or participant data is automatically imported into this edition.

## Honest recovery and privacy

Requests are pinned to the accepted conversation and CID before submission.
Unknown message/answer submission is never rerouted or automatically retried.
Telegram sends are reserved durably before transport; a missing delivery
acknowledgment is uncertain, not safe to resend. Completed duplicate recovery
links to Möbius instead of reading owner-only transcripts or rerunning work.
Queued messages and answer turns without new work link to Möbius rather than
consume a different turn's stream. A stream ending or `running: false` is not
proof that work, a Goal, or a privileged action succeeded.

The reviewed background job reads its own encrypted bot key into **RAM only**
for a fixed HTTPS Telegram origin and a canonical method allowlist. Browser
frames cannot decrypt keys; no service is declared by Bridge. No redirect,
proxy environment, credential echo or raw exception is forwarded to the frame.
Telegram processes Telegram requests; configured providers process Möbius
requests. Hosting operators control the machine; this is not encryption from
its operator. Store/source packages contain no keys, pairings or histories.

Only Python's standard library is needed by listener/transport. The explicitly
owner-invoked sealed setup helper uses the deployed platform Python and existing
public backend primitives, not ambient provider packages or CLI credentials.
Keep the existing MIT attribution in `LICENSE`; dependency and third-party notices retain their own terms.

See [COMPATIBILITY.md](COMPATIBILITY.md) for the exact feature matrix. See TESTING.md for the repeatable synthetic suite.
