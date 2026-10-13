import argparse
import getpass
import json
import sys
from dataclasses import asdict

from .auth import Keychain, interactive_login
from .models import IntegrationError, ProposalInput, ScoreInput
from .runtime import runtime


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
        if args.command == "login":
            username = input("TennisRungs username: ")
            password = getpass.getpass("TennisRungs password (not stored): ")
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
