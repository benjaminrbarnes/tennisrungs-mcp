import argparse
import getpass
import json
import sys
import warnings

from .auth import Keychain, interactive_login
from .models import AuthenticationRequired, IntegrationError, ProposalInput, ScoreInput
from .runtime import runtime


def prompt_credentials():
    if not sys.stdin.isatty():
        raise AuthenticationRequired("Open a local Terminal for non-echo credential entry; redirected input is refused")
    username = input("TennisRungs username: ")
    try:
        with warnings.catch_warnings():
            # getpass otherwise falls back to echoing input. Never allow that.
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("TennisRungs password (hidden; not stored): ")
    except (getpass.GetPassWarning, EOFError):
        raise AuthenticationRequired("A secure non-echo terminal prompt is unavailable") from None
    return username, password


def main(argv=None):
    p = argparse.ArgumentParser(description="Direct HTTP TennisRungs. No browser automation.")
    p.add_argument("--keychain", action="store_true", help="Read an explicitly approved local session")
    p.add_argument("--enable-writes", action="store_true")
    p.add_argument("--state-dir", help="Local journal directory; never inside version control")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ["ladders", "matches", "own-proposals", "open-proposals"]:
        sub.add_parser(name)
    for name, field in [("rankings", "ladder_id"), ("history", "team_id")]:
        sub.add_parser(name).add_argument(field, type=int)
    ip = sub.add_parser("iparcs", help="Anonymous Atlanta court reads; no bookings or credentials")
    ips = ip.add_subparsers(dest="ip_command", required=True)
    ips.add_parser("search").add_argument("keyword")
    ips.add_parser("detail").add_argument("resource_id", type=int)
    av = ips.add_parser("availability")
    av.add_argument("resource_id", type=int)
    av.add_argument("start_date")
    av.add_argument("end_date")
    slot = ips.add_parser("check-slot")
    slot.add_argument("resource_id", type=int)
    slot.add_argument("day")
    slot.add_argument("start_time")
    slot.add_argument("end_time")
    login = sub.add_parser("login", help="Interactive normal login; never reads browser credentials")
    login.add_argument("--approve-session-storage", action="store_true", required=True,
                       help="Explicitly approve storing resulting site session in macOS Keychain")
    for name in ["propose", "score"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--input", required=True, help="JSON file containing non-secret match/score fields")
        cmd.add_argument("--operation-key", required=True)
        cmd.add_argument("--confirm", action="store_true", required=True)
    cmd = sub.add_parser("withdraw")
    cmd.add_argument("challenge_id", type=int)
    cmd.add_argument("--operation-key", required=True)
    cmd.add_argument("--confirm", action="store_true", required=True)
    cmd.add_argument("--human-confirmed-race-risk", action="store_true", required=True,
                     help="Manual action only; acceptance may race with withdrawal")
    cmd = sub.add_parser("accept")
    for field in ["challenge_id", "ladder_id", "team_id"]:
        cmd.add_argument(field, type=int)
    cmd.add_argument("--operation-key", required=True)
    cmd.add_argument("--confirm", action="store_true", required=True)
    args = p.parse_args(argv)
    client = None
    try:
        if args.command == "iparcs":
            from .iparcs_reads import IParcsReads
            iparcs = IParcsReads()
            if args.ip_command == "search":
                result = iparcs.search(args.keyword)
            elif args.ip_command == "detail":
                result = iparcs.detail(args.resource_id)
            elif args.ip_command == "availability":
                result = iparcs.availability(args.resource_id, args.start_date, args.end_date)
            else:
                result = iparcs.check_slot(args.resource_id, args.day, args.start_time, args.end_time)
            print(json.dumps(result.to_dict(), indent=2))
            return 0
        if args.command == "login":
            username, password = prompt_credentials()
            cookies = interactive_login(username, password)
            Keychain().store(cookies)
            print(json.dumps({"session_stored": True, "storage": "macOS Keychain", "service": "tennisrungs-mcp.session.v1"}))
            return 0
        client = runtime(use_keychain=args.keychain, writes=args.enable_writes, state_dir=args.state_dir)
        reads = {"ladders": client.list_current_ladders, "matches": client.list_own_matches,
                 "own-proposals": client.list_own_proposals, "open-proposals": client.list_open_proposals}
        if args.command in reads:
            result = reads[args.command]()
        elif args.command == "rankings":
            result = client.get_rankings(args.ladder_id)
        elif args.command == "history":
            result = client.get_player_history(args.team_id)
        elif args.command in ["propose", "score"]:
            with open(args.input) as f:
                fields = json.load(f)
            if args.command == "propose":
                result = client.propose_match(ProposalInput(**fields), args.operation_key, confirmed=args.confirm)
            else:
                result = client.report_score(ScoreInput(**fields), args.operation_key, confirmed=args.confirm)
        elif args.command == "withdraw":
            result = client.withdraw_proposal(args.challenge_id, args.operation_key, confirmed=args.confirm, autonomous=False)
        elif args.command == "accept":
            result = client.accept_proposal(args.challenge_id, args.ladder_id, args.team_id, args.operation_key, confirmed=args.confirm)
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    except IntegrationError as e:
        print(json.dumps({"error": type(e).__name__, "message": str(e)}), file=sys.stderr)
        return 2
    except (ValueError, TypeError, OSError):
        print(json.dumps({"error": "InvalidInput", "message": "Invalid local input; values suppressed"}), file=sys.stderr)
        return 2
    finally:
        if client:
            client.transport.close()
            if client.journal:
                client.journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
