"""Entirely synthetic data. No downloaded account pages or real identities."""

LADDER = '''<fieldset><legend>MY CURRENT LADDERS</legend><a href="/Ladders/Rankings/101">Demo Fall Singles</a></fieldset>'''


def dashboard(status="PROPOSED", cid=303, when="10/20/2099 10:00 AM", own=True, proposal=True):
    row = f'''<tr><td>Demo Fall Singles</td><td><a href="/Public/PlayerMatches?teamId=202">Demo Opponent</a></td>
    <td>{status} Scheduled For: {when} Location: Demo Court</td><td>
    <a href="/Player/SubmitChallengeResult?ladderId=101&amp;challengeId={cid}">Report Score</a>
    <a onclick="tr.WithdrawChallenge(this,{cid})">Withdraw</a></td></tr>''' if own else ""
    prop = '''<tr><td>Demo Player</td><td>Demo Fall Singles</td><td>10/20/2099 10:00 AM @ Demo Court</td>
    <td><a onclick="tr.PostJson('/Player/AcceptProposal?cId=303&amp;acceptedBy=201',true)">Accept</a></td></tr>''' if proposal else ""
    return LADDER + f'''<a>My Challenges ({1 if own else 0})</a><a>Open Proposals({1 if proposal else 0})</a>
    <div id="tabs-1"><table><tr><th>Ladder</th><th>Opponent</th><th>Status</th></tr>{row}</table></div>
    <div id="tabs-5"><table>{prop}</table></div>'''


RANKINGS = '''<button onclick="tr.ShowProposeMatch(201,this)">Propose Match</button>
<table><tr><th>Rank</th><th>Player</th><th>USTA Rating</th><th>Record</th><th>Points</th><th>Streak</th><th>Movement</th></tr>
<tr><td>#1</td><td><a href="/Public/PlayerMatches?teamId=201">Demo Player</a></td><td>3.0</td><td>2 - 1</td><td>18</td><td>W1</td><td>Up</td></tr></table>'''

HISTORY = '''<table><tr><th>Date</th><th>Vs.</th><th>Result</th><th>Score</th></tr>
<tr><td>10/1/2099</td><td>#2 <a href="/Public/PlayerMatches?teamId=202">Demo Opponent</a></td><td>L</td><td>6-3,7-6 (10-8)</td></tr>
<tr><td>10/2/2099</td><td><a href="/Public/PlayerMatches?teamId=203">Demo Other</a></td><td>W</td><td>3-6,6-2,5-2Forfeit</td></tr></table>'''
