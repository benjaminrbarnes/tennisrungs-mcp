"""Local login and read-only TennisRungs commands."""
import argparse
import getpass
import json
import sys
import warnings

from .auth import Keychain, interactive_login
from .models import AuthenticationRequired, IntegrationError
from .runtime import runtime


def prompt_credentials(site_label="TennisRungs"):
    if not sys.stdin.isatty():
        raise AuthenticationRequired("Open a local Terminal for non-echo credential entry; redirected input is refused")
    username = input(f"{site_label} username: ")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass(f"{site_label} password: ")
    except (getpass.GetPassWarning, EOFError):
        raise AuthenticationRequired("Secure non-echo credential prompt unavailable") from None
    return username, password


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local login and read-only TennisRungs CLI")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--keychain", action="store_true", help="Use a legacy macOS Keychain session")
    group.add_argument("--file-session", action="store_true", help="Use the private session created by login")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["ladders", "matches", "own-proposals", "open-proposals"]:
        sub.add_parser(name)
    sub.add_parser("rankings").add_argument("ladder_id", type=int)
    sub.add_parser("history").add_argument("team_id", type=int)
    login = sub.add_parser("login", help="One normal login; the website password is not stored by default")
    login.add_argument("--approve-session-storage", action="store_true", required=True,
                       help="Allow storing the verified session in the private file or explicitly selected Keychain")
    login.add_argument("--credential-provider", choices=["local-file"],
                       help="Opt in to renewal using a previously configured password file, without prompt fallback")
    credentials = sub.add_parser("credentials", help="Optional private password storage for unattended renewal")
    bootstrap = credentials.add_subparsers(dest="credential_command", required=True).add_parser("bootstrap")
    bootstrap.add_argument("--approve-plaintext-storage", action="store_true", required=True)
    args = parser.parse_args(argv)
    client = None
    try:
        if args.command == "credentials":
            from .local_credentials import bootstrap
            print(json.dumps(bootstrap(approve_plaintext_storage=args.approve_plaintext_storage), indent=2))
            return 0
        if args.command == "login":
            if args.credential_provider:
                if args.keychain:
                    raise AuthenticationRequired("Local-file renewal cannot select Keychain")
                from .local_credentials import renew
                result = renew("tennisrungs", store_session=True)
                print(json.dumps(result, indent=2))
                return 0 if result["status"] == "OK" else 2
            username, password = prompt_credentials()
            cookies = interactive_login(username, password)
            if args.keychain:
                Keychain().store(cookies)
            else:
                from .file_sessions import FileSessionStore
                FileSessionStore("tennisrungs").store(cookies)
            print(json.dumps({"session_stored": True, "storage": "macOS Keychain" if args.keychain else "private-file"}))
            return 0
        client = runtime(use_keychain=args.keychain, use_file_session=args.file_session)
        reads = {"ladders": client.list_current_ladders, "matches": client.list_own_matches,
                 "own-proposals": client.list_own_proposals, "open-proposals": client.list_open_proposals}
        if args.command in reads:
            result = reads[args.command]()
        elif args.command == "rankings":
            result = client.get_rankings(args.ladder_id)
        else:
            result = client.get_player_history(args.team_id)
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    except IntegrationError as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2
    except (ValueError, TypeError, OSError):
        print(json.dumps({"error": "InvalidInput", "message": "Invalid local input; values suppressed"}), file=sys.stderr)
        return 2
    finally:
        if client:
            client.transport.close()


if __name__ == "__main__":
    main()
