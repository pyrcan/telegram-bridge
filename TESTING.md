# Source-only, offline verification

Use Python 3.12 and pytest. Run from this repository's root; all credentials,
Telegram identities, chats, cards and providers in the tests are fictional.
Do not supply real keys, participant data, inherited app/job/owner credentials,
or an installed app URL. No Telegram/provider request, consumer subprocess,
app apply, publication, browser or live storage mutation is required.

## App guards

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  test_bridge.py test_bridge_loop.py test_bridge_progress.py
```

The tests fail on unmocked socket connections and urllib HTTP. Fake openers are
explicit; they cannot fall through to HTTP. Coverage includes:

- Canonical fixed Telegram methods/origin, request/response limits, no proxies
  or redirects, bounded poll timeout, safe errors and nested escaped key echoes.
- Named own-job secret reads, RAM key-change fencing, safe bot projection and
  setup's different-bot refusal without starting listening.
- One private paired owner, consumed pairing code, foreign/group rejection,
  fresh own-app/scope routing, read-only browsing and ordered explicit routing.
- Exact saved-card identities, canonical strings, actual button option IDs,
  typed/mixed prose never becoming consent, newer-card reconciliation, absent
  status failing closed, 409 preservation and uncertain CID/delivery fencing.
- Accidental bot-key-looking Telegram input becomes a content-free, ordered
  rejected-input receipt **before** durable intake or receive-cursor advance.
  Rejection cannot change pairing, card answers or routing, or invoke a model.
- Private media removed from noncanonical question lead/baseline and reply
  drafts. Canonical private-media cards redirect to the original card rather
  than reinterpret its prompt/options. No media token or file fetch is made.
- Public event-log streaming; sensitive approval/secure cards redirect; a 204
  or lost stream is unknown, not success. Queued/duplicate recovery does not
  read owner transcripts or resubmit work.
- Durable inbox/restart order, pause/revocation, cursor-before-ack constraints,
  bounded cosmetic acknowledgement lane, independent read controls, optional
  menu failure, coalesced progress and shutdown, content-free status locking.
- Optional Studio contract marker and fresh matching service/runtime checks;
  no dependency installation, participant projection or authority escalation.
- Removed feature callers/permissions and credential input controls stay absent.

Running `python3 -m pytest` over all test files without the isolated platform
wrapper intentionally skips the public-core integration module. That skip is
**not** proof of the core boundary; run the following separate command too.

## Actual public-core contracts

Use a reviewed public Möbius checkout at
`9ebca6c8584400e6adc419ee8196a0fb82d19896` (or independently review a newer one).
Prepare its backend environment from `backend/requirements.lock` and frontend
compiler dependencies from `frontend/package-lock.json`, following that
checkout's instructions. These setup steps are not performed by the tests.
The listener itself has no third-party Python dependency.

```sh
BRIDGE_SOURCE="$(pwd)"
MOBIUS_PLATFORM_SOURCE=/absolute/path/to/reviewed/public/mobius
(
  cd "$MOBIUS_PLATFORM_SOURCE"
  PYTHONDONTWRITEBYTECODE=1 SECRET_KEY=synthetic-public-test-key \
    ./scripts/wt-pytest.sh "$BRIDGE_SOURCE/test_bridge_public_contracts.py" -q
)
```

Use **this wrapper**, not a direct pytest invocation with production backend
configuration. It establishes disposable DB/data/runtime paths before imports.
The integration module requires its isolation marker, imports the public test
fixtures before any backend module, and replaces the deployed helper's import
seam with the checkout's actual auth, database and runtime primitives.

The integration uses real public saved-card authoring, public UUID/card
normalization, writer Claim/Settle admission, principal validation, app token
creation, secret/storage routes and encrypted-at-rest storage. The actual app
sealed consumer runs against only an in-process TestClient and an explicit
synthetic Telegram opener. It checks pending vs consuming, exact current card,
command/cwd/author-run/nonce/runtime and guest provenance; completed receipts
cannot be consumed again. Submitted synthetic values are absent from transcripts
and output. Its short-lived ordinary app token has neither service/job/owner
claims and cannot read secrets. Separate tests prove named-job grant intersection,
revocation and inability of frame/job principals to mint job authority; actual
public answer validation distinguishes prose from explicit quiet-close choices.

For upstream regression coverage, run a **separate** wrapper invocation:

```sh
(
  cd "$MOBIUS_PLATFORM_SOURCE"
  PYTHONDONTWRITEBYTECODE=1 SECRET_KEY=synthetic-public-test-key \
    ./scripts/wt-pytest.sh tests/test_app_secrets.py \
    tests/test_saved_secure_inputs.py -q
)
```

Do not collect the external integration file and `backend/tests` together:
registering the same public conftest twice is a pytest plugin error, not an
application failure. Report any wrapper dependency-lock warning; an image-only
fallback with a different lock is not dependency-authoritative evidence.

## Public manifest/source validator and exact production compile

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  "$MOBIUS_PLATFORM_SOURCE/backend/scripts/validate-app.py" "$BRIDGE_SOURCE"
```

This uses public source completeness, manifest/static reference checks and the
installer's actual locked JSX compiler. It neither applies the app nor calls an
API. An environment/compile-stall exit is inconclusive, not a pass. Off-origin
`t.me` references are navigation links, never frame credential transport.
Repository tests are developer files, not runtime `source_files` inputs. Keep
private receipts, environments, generated bundles and logs outside the package.

## Coherent replacement of the 0.1.0 baseline suite

The comparison baseline is public commit
`3008baa3ceff94aecd7d7f9fd24e0d35520fcb5d`; use that Git object, not a mutable
working-tree copy. No old test should be left asserting an endpoint/permission
that this edition does not ship.

| Baseline test family | Replacement / reason |
|---|---|
| `test_bridge.py`, transport and setup tests | Retained canonical transport, pairing, cards, text, media privacy, model/routing guard and delivery invariants in `test_bridge.py`; supported sealed setup now additionally exercises actual public primitives. |
| `test_bridge_loop.py`, `test_bridge_progress.py` | Preserve durable intake, ordering, responsiveness, bounded acknowledgement and progress regressions. Navigation origin is now accepted job context, never editable storage. Add rejected-input privacy coverage. |
| Assistant navigation / connection tests | Retain fresh optional Studio checks, metadata-only navigation, own routing and status locking. Studio customization continuation and app service bot-info do not ship. |
| Access tests and browser access-flow fixture | No Bridge grant writer, user-management controls or access service exists. Replace with absence-of-permission/caller assertions and paired-owner/uncertain-delivery guards; do not copy obsolete browser fixtures. |
| Completed transcript recovery / query snapshot / rich draft tests | Those contracts are unavailable or omitted. Replace with no transcript read/no rerun, public event-log mode, unknown-result handoff and bounded supported drafts. |

These are source regression tests, not end-to-end Telegram/client, provider,
phone delivery, UI screenshot or publication proof. They do not establish that
an arbitrary new platform version is compatible. Never weaken a failing guard
with an xfail, fallback bearer, broader permission or live operation.
