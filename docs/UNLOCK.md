# Secure Windows unlock (optional, disabled by default)

Lets the Android app unlock the PC's **own already-signed-in console session** - not a new session, not RDP -
using the Windows PIN/password typed on the phone, a phone fingerprint, or both. Windows performs the actual
authentication; this project never checks a password itself.

**Status: `REMOTE_PC_UNLOCK=0` by default.** Nothing in this feature runs until you build, sign and register the
Windows component below and set the environment variables. Read "Known limitations" before relying on it.

## How it works

```
Android app --HTTPS/WSS, authenticated--> FastAPI agent --local named pipe--> Credential Provider --LSA--> Windows
```

- The agent (`backend/app/unlock.py`) never stores a Windows password. It holds only: enrolled devices' **public**
  keys, short-lived biometric challenges, and a rate limiter. The PIN/password passed in a request lives in memory
  for the length of one unlock attempt and is zeroed immediately after.
- The Windows-side component (`windows/unlock-provider/`) is a `CPUS_UNLOCK_WORKSTATION` Credential Provider -
  Microsoft's documented extension point for this exact scenario. It adds one extra tile to the **existing** lock
  screen, only while a request is pending; the built-in password tile is untouched. Windows (LSA) does the real
  authentication, with normal lockout/policy enforcement, and only Windows' own result is ever reported back.
- Because the provider only fires for `CPUS_UNLOCK_WORKSTATION` and binds the Windows session ID, the target is
  always the console session already showing the lock screen - never a new/RDP session.

## Two unlock modes

1. **PIN/password** - the phone sends the credential directly over the authenticated HTTPS/WSS connection used by
   the rest of the app (a separate endpoint, never the screen-input WebSocket). Windows validates it.
2. **Biometric** - the phone's fingerprint unlocks a hardware-backed Android Keystore key (`BiometricPrompt`,
   `setUserAuthenticationRequired`, `setInvalidatedByBiometricEnrollment`) that signs a fresh, PC-issued, single-use
   challenge bound to this PC, this account, this Windows session, and a short expiry. **A successful fingerprint
   scan is never treated as a Windows logon by itself** - the signed challenge still only *authorizes sending* the
   Windows credential, which Windows still has to accept. Set `REMOTE_PC_UNLOCK_REQUIRE_BIOMETRIC=1` to require
   both factors together.

## Requirements

- Windows 11 Pro, the PC's own local (non-domain) account for now - see limitations.
- Visual Studio 2022 (Desktop C++ workload) + Windows 10/11 SDK, to build `windows/unlock-provider/`.
- A code-signing certificate. A self-signed test cert works for your own machine; anything you'd trust long-term
  should use a real one (or enable test-signing mode, which you should not leave on permanently).

## Install

1. **Build the provider** (on the Windows PC, in an "x64 Native Tools" prompt):
   ```powershell
   cd windows\unlock-provider
   cmake -B build -A x64
   cmake --build build --config Release
   signtool sign /fd SHA256 /a build\Release\RemoteUnlockProvider.dll   # or your own signing step
   ```
2. **Register it** (as Administrator): `.\register.ps1 -DllPath .\build\Release\RemoteUnlockProvider.dll`
   Then lock the PC and confirm the normal password tile still works and no extra tile appears (none should,
   since nothing is enabled yet).
3. **Enable the feature** in `.env`:
   ```
   REMOTE_PC_UNLOCK=1
   REMOTE_PC_UNLOCK_ACCOUNT=<your Windows username>
   REMOTE_PC_UNLOCK_REQUIRE_BIOMETRIC=0
   ```
   Restart the agent. `GET /api/v1/unlock/status` should now report `"integration_installed": true`.
4. **Enroll your phone**: in the app, Dashboard -> Unlock -> "Enroll this phone" generates a device key and calls
   `POST /api/v1/unlock/devices`. It comes back `PENDING_LOCAL_APPROVAL` - nothing works yet.
5. **Approve it, on the PC, locally** (this step is deliberately not reachable over the network):
   ```
   python -m app.unlock_admin list
   python -m app.unlock_admin approve <device-id-or-fingerprint-shown-in-the-app>
   ```
6. Lock the PC and try both "Unlock with PIN/Password" and "Unlock with Fingerprint" from the app.

## Revoking a lost phone

`python -m app.unlock_admin revoke <device-id>` on the PC (or `DELETE /api/v1/unlock/devices/{id}` over the
authenticated API from another enrolled, trusted session) immediately invalidates that device's key; any
in-flight challenge for it is dropped too.

## Uninstall / recovery

- Set `REMOTE_PC_UNLOCK=0` (or delete it) in `.env` and restart the agent - the feature stops responding, but the
  provider stays registered and harmless until you also remove it.
- Remove the Windows component: `windows\unlock-provider\uninstall.ps1` (as Administrator). This only deletes two
  registry keys; it never touches your account password, BitLocker, or any other credential provider. Stock
  Windows sign-in is unaffected the whole time this feature has existed - it only ever **adds** an extra tile.
- If you are ever locked out for an unrelated reason, use Windows' normal recovery path (Safe Mode, a recovery
  drive, another administrator account) - this feature has no special access that bypasses that.

## Known limitations / what is NOT done here

- **The Windows Credential Provider source is unverified.** It was written against Microsoft's documented
  `ICredentialProvider`/`ICredentialProviderCredential` interfaces for `CPUS_UNLOCK_WORKSTATION`, but there is no
  Windows/MSVC toolchain in the environment that produced it, so it has not been compiled, signed, or exercised
  against a real lock screen. **Do not consider Windows unlock functional until you have built it and verified it
  yourself on a disposable Windows 11 VM you can snapshot/roll back**, before ever registering it on a machine you
  depend on.
- Local accounts only for now; Microsoft/domain accounts need a different `LogonDomainName`/authentication-package
  setup in `GetSerialization` that is not implemented.
- One Windows account per PC (`REMOTE_PC_UNLOCK_ACCOUNT`); multi-account selection is not implemented.
- `python -m app.unlock_admin approve` must be run locally on the PC - by design, so pairing a new phone always
  needs physical/already-authenticated access to the machine, not just the API token.
- The agent-side rate limiting and challenge store are in-memory and per-process; they reset on restart.
