# Sanitized implementation evidence

Research date: 2026-10-13. No credential values or real match fixtures included.

## Direct HTTP versus browser observations

Anonymous public history and public pending-challenges HTML were read using normal
HTTP. The new client also successfully parsed a public history response in a live
read-only smoke test. `/Player`, membership, rankings, proposals and score-entry
forms were inspected in an already signed-in browser through supported DOM reads.
Authenticated network requests, headers, cookies and token lifecycle were not
observable through that tool. An anonymous Python account-page request returned
403. No alternate credential/session extraction channel was used.

The normal public `/Account/Login` page was independently read through the new
HTTP transport: HTTP 200, form method POST, action `/Account/Login`, fields
`UserName`, `Password`, `remember`, no hidden inputs, and no Set-Cookie response.
No credentials were submitted. This establishes the normal login form contract,
but not authenticated cookie names or successful session renewal.

## Contracts

| Operation | Route | Evidence | Live new-client validation |
|---|---|---|---|
| Account lists | GET `/Player` | Signed-in browser DOM | Blocked on auth |
| Rankings | GET `/Ladders/Rankings/{ladder}` | Signed-in browser DOM | Blocked on auth |
| Player history | GET `/Public/PlayerMatches?teamId={team}` | Browser and anonymous HTTP | Passed |
| Proposal form | GET `/Player/ProposeMatch/{season-team}` | Live DOM/form | Blocked on auth |
| Propose | POST `/Player/ProposeMatch?{serializedForm}` | Inline frontend handler | Offline only |
| Withdraw | POST `/Player/WithdrawChallenge`, form `challengeId` | Public frontend source/DOM | Offline only |
| Accept proposal | POST `/Player/AcceptProposal?cId=…&acceptedBy=…` | Live DOM handler + PostJson source | Offline only |
| Score form | GET `/Player/SubmitChallengeResult?ladderId=…&challengeId=…` | Live DOM | Blocked on auth |
| Report score | POST `/Team/SubmitChallengeScore` | Public frontend source + live route config | Offline only |

Proposal form fields: `TeamId`, `Location`, `MatchDate`, `PreferredLocation`, `Hour`,
`Minute`, `AmOrPm`, `ShowMyEmail`. Checkbox fallback duplicates are preserved.
Proposal end time is not structured. Hidden form fields are preserved dynamically
without logging; no actual anti-forgery field requirement was established.

Scores use `score`, `challengeid`, `matchOutcome`, `winnerId`. Observed outcome
values: `PlayedThrough`, `Injury`, `Forfeit`, `NoShow`, `CourtTimeExpired`.
History exposes separate result orientation and original score strings. Do not
derive winner identity from the first numbers in a history score string.

## Unknowns

- Actual session-cookie names, flags, expiration and server revocation.
- Direct login compatibility and any anti-forgery/header/origin requirements.
- Server idempotency, duplicate prevention and live write-response variants.
- Whether withdrawal refuses an already accepted proposal. The visible request
  has only `challengeId`; no expected-state/version condition. A preceding read
  does not remove the acceptance race. Autonomous cancellation is disabled.
- Official developer API support or authorization for private endpoint use.
- Rate quotas, pagination variants and all scoring configurations.

References: [public frontend](https://app.tennisrungs.com/Scripts/tr.js?rev=04242016),
[product](https://info.tennisrungs.com/),
[terms](https://www.tennisrungs.com/Home/TermsOfService).

## Existing workflow preserved

The existing agent verifies current season IDs, keeps an independent per-date
approval/ledger, observes an all-in booking ceiling, and checks acceptance before
court submission. The rolling 72-hour booking guard (with a conservative 15-minute
margin) is agent workflow policy, not a TennisRungs challenge deadline. This repo
does not alter skills, jobs, memories, calendars or live match operations.

Atlanta's verified portal is
`https://anc.apm.activecommunities.com/atlantadprca/reservation/landing`.
A paid tentative permit is pending staff approval. The official ACTIVE Net System
API requires licensed organization access and signing credentials; the iParcs
adapter is intentionally separate.
