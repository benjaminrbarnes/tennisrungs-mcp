# Tests requiring specific permission

No production write is authorized by a development test or fixture.

1. **Authentication:** approve a single normal interactive login to TennisRungs
   and session storage in macOS Keychain under `tennisrungs-mcp.session.v1`.
   Verify the authenticated identity/current membership through direct HTTP.
   Inspect only sanitized cookie names/flags and actual hidden-field names; never
   export secret values. Stop on security challenges or denied access.
2. **Proposal creation/withdrawal:** prefer a vendor test ladder with a designated
   test account and consenting second participant. Approve exact ladder, season
   team, venue ID, real date/time, note, email disclosure, notification recipients,
   one POST and one cleanup withdrawal. No fake public match. On production,
   choose a match the account holder actually intends to play and accept that it
   may be accepted before cleanup. Never reuse an existing active match as a test.
3. **Race test:** with vendor permission, accept that test proposal concurrently
   with withdrawal. Determine whether the server rejects withdrawal of accepted
   proposals or supports atomic expected-state/version checks. Do not enable
   autonomous cancellation from a successful sequential test alone.
4. **Acceptance:** specifically approve one selected consenting test proposal
   and its exact participant/season scope. Cleanup must be planned with that
   participant; acceptance affects a second person.
5. **Score:** use a completed designated test match with an agreed actual winner,
   sets, tiebreaks and outcome. Approve submission and any correction process.
   Never fabricate a score in a live ladder. Establish a challenge-specific
   read-back contract before upgrading acknowledged scores to verified.
6. **Failure handling:** simulate timeout, login expiry and process interruption
   offline first. If a live response is lost, read the account once and reconcile
   the journal. Do not intentionally issue a second POST to test duplicates.

Later test permissions must identify the concrete fixture and cleanup, rather
than granting blanket write access. No iParcs checkout/payment is part of this plan.
