# Supported public-core edition boundary

Public reference: official `9ebca6c8584400e6adc419ee8196a0fb82d19896`.
No core changes, legacy endpoint adapter, hidden fallback, new permission or
migration to the live/full app is included.

| Feature | This edition |
|---|---|
| Current Chats/Bots/Tools presentation | Retained with the same Bridge visual vocabulary; simplified controls |
| Dedicated personal bot / one paired private owner | Retained; groups/foreign accounts ignored; code consumed |
| Key setup | Existing saved sealed-input owner-chat workflow; no app key input/transcript paste |
| Runtime key boundary | Public named job-secret read; key is RAM-only for canonical HTTPS Telegram methods |
| Ordinary owner Telegram text | Bridge-owned app-chat messages + event-log SSE only |
| Menu/status/model chooser | Retained; model changes create a fresh chat, preserve old ones |
| Reply progress | Bounded coalesced optional drafts/typing; independent of final delivery |
| Durable receive + ordered work | Retained; saved inbox before cursor advance; read-only controls may overtake work |
| Saved ordinary card controls | Exact canonical card/option identities and paired binding; agent-scoped, not trusted owner authority |
| Oversized/free-text-only/secure/typed action cards | Open the original card in Möbius; no partial reinterpretation |
| Bridge-owned routing | Fresh own-app/scope metadata, explicit Continue here; pending-card switch guard |
| Archive/Restore/Delete/Undo, Active/Archived categories | Omitted; public app metadata does not reveal filing state and no app filing capability exists |
| Transcript/recent-text preview, completed-result history reader | Omitted; public app tokens cannot read owner transcript endpoints |
| Completed duplicate / queued / uncertain recovery | Pin original CID/chat; no rerun/reroute/automatic resend; deep-link to Möbius |
| Optional Studio metadata shortcuts | Only already-authorized `owner-metadata-v1` catalog plus fresh matching app/service/runtime identity; no dependency assumption |
| Studio setup/publish/access management and request alerts | In Studio/Möbius only; no Bridge grant writer or user-management controls |
| Exact owner customization-chat grants / continuation | Omitted; opening canonical editing chat is navigation only |
| Telegram Mini App and panel enable/disable | Omitted coherently, including HTML, descriptors and callers |
| Owner actions, delegated owner action runtime | Omitted; sealed setup is a real owner-chat saved input, not a forged action flag |
| Screenshots, media download/send, file/text-serving descriptors | Omitted; private artifacts open in Möbius after sign-in |
| Topics, group/forum routes | Omitted; one private owner account only |
| Provider/Telegram live verification | Not performed; synthetic tests cannot prove phone behavior or delivery |

The manifest declares only supported runtime inputs. Store screenshots use
fictional data and are not runtime inputs. MIT attribution is retained. No
credentials, pairings, grants, histories or caches are included. Synthetic tests
are repository-only developer files, not installed app source inputs.
