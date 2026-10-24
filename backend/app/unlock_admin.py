"""Local administrator tool for unlock devices (run on the PC, never reachable over the network).

    python -m app.unlock_admin list
    python -m app.unlock_admin approve <device-id or fingerprint>
    python -m app.unlock_admin revoke <device-id>
"""
import sys
from .unlock import service

def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("list", "approve", "revoke") or (argv[0] != "list" and len(argv) != 2):
        print(__doc__); return 2
    if argv[0] == "list":
        for d in service.list_devices(): print(f'{d["device_id"]}  {d["status"]:<9} {d["fingerprint"]}  {d["name"]}')
        return 0
    ok = service.approve(argv[1]) if argv[0] == "approve" else service.revoke(argv[1])
    print("done" if ok else "no matching device"); return 0 if ok else 1

if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))
