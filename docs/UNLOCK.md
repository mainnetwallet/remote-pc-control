# Secure Windows Unlock

> **Optional. Disabled by default.** Nothing in this feature runs until you build the Windows
> component, register it, and set `REMOTE_PC_UNLOCK=1`. See [Status](#status) below.

Lets the Android app unlock the PC's **own already-signed-in console session** — not a new
session, not RDP — using the Windows PIN/password typed on the phone, a phone fingerprint, or
both. **Windows performs the actual authentication; this project never checks a password itself.**

### Contents

- [Status](#status)
- [How it works](#how-it-works)
- [Unlock modes](#unlock-modes)
- [Requirements](#requirements)
- [Install](#install)
- [Revoking a lost phone](#revoking-a-lost-phone)
- [Uninstall / recovery](#uninstall--recovery)
- [Known limitations](#known-limitations--what-is-not-done-here)

---

## Status

| | |
|---|---|
| Default state | `REMOTE_PC_UNLOCK=0` — feature is off |
| Turns on after | Build + register the Windows component, then set the env vars (see [Install](#install)) |
| Before relying on it | Read [Known limitations](#known-limitations--what-is-not-done-here) |

---

## How it works

```
Android app --HTTPS/WSS, authenticated--> FastAPI agent --local named pipe--> Credential Provider --LSA--> Windows
```

| Component | What it does |
|---|---|
| Agent (`backend/app/unlock.py`) | Never stores a Windows password. Holds only enrolled devices' **public** keys, short-lived biometric challenges, and a rate limiter. A submitted PIN/password lives in memory for one unlock attempt only and is zeroed immediately after. |
| Windows component (`windows/unlock-provider/`) | A `CPUS_UNLOCK_WORKSTATION` Credential Provider — Microsoft's documented extension point for exactly this scenario. Adds **one extra tile** to the existing lock screen, only while a request is pending; the built-in password tile is untouched. |
| Windows (LSA) | Does the real authentication — normal lockout/password policy enforcement applies. Only Windows' own result is ever reported back. |

Because the provider only fires for `CPUS_UNLOCK_WORKSTATION` and binds the Windows session ID,
the target is always the console session already showing the lock screen — **never** a new or
RDP session.

---

## Unlock modes

**1. PIN/password**
The phone sends the credential directly over the authenticated HTTPS/WSS connection used by the
rest of the app (a dedicated endpoint — never the screen-input WebSocket). Windows validates it.

**2. Biometric**
The phone's fingerprint unlocks a hardware-backed Android Keystore key (`BiometricPrompt`,
`setUserAuthenticationRequired`, `setInvalidatedByBiometricEnrollment`) that signs a fresh,
PC-issued, single-use challenge bound to this PC, this account, this Windows session, and a short
expiry.

> **A successful fingerprint scan is never treated as a Windows logon by itself.** The signed
> challenge only *authorizes sending* the Windows credential — Windows still has to accept it.
> Set `REMOTE_PC_UNLOCK_REQUIRE_BIOMETRIC=1` to require both factors together.

---

## Requirements

- Windows 11 Pro, the PC's own **local** (non-domain) account for now — see [limitations](#known-limitations--what-is-not-done-here).
- Visual Studio 2022 (**Desktop development with C++** workload) + Windows 10/11 SDK, to build
  `windows/unlock-provider/`. This is what gives you `cmake` and `signtool` — they do **not**
  exist in a plain PowerShell or cmd window.
- A code-signing certificate. A self-signed test cert works for your own machine; anything you'd
  trust long-term should use a real one (or enable test-signing mode, temporarily — see step 0 below).

---

## Install

### Step 0 — `cmake` / `signtool` not recognized?

If PowerShell says `cmake` or `signtool` is "not recognized as the name of a cmdlet...", you're in
a **plain** PowerShell window. Those tools only live inside the Visual Studio developer shell.

1. Install **[Visual Studio 2022 Community](https://visualstudio.microsoft.com/downloads/)** (free).
   In the installer, select the **"Desktop development with C++"** workload — this pulls in
   CMake, MSVC, and the Windows SDK (which includes `signtool.exe`) together.
2. Open Start → **"x64 Native Tools Command Prompt for VS 2022"** (or *"Developer PowerShell for
   VS 2022"**) instead of a normal terminal. Both tools are on `PATH` automatically there. Run
   every command below from this shell.
3. *(Optional, for a quick local test build only)* Skip real code-signing with test-signing mode:
   ```powershell
   # elevated Native Tools shell, then reboot
   Bcdedit /set testsigning on
   ```
   Windows will then load the unsigned DLL — skip the `signtool sign ...` line in step 1 below.
   Turn it back off when you're done (`Bcdedit /set testsigning off` + reboot); don't leave it on.

### Step 1 — Build the provider

The Native Tools shell opens in the Visual Studio install folder, **not your repo** — `cd` to the
repo's full path first, or `cd windows\unlock-provider` will fail with "The system cannot find
the path specified" (and a bare `cmake -B build -A x64` run from the wrong folder will then fail
too, with "does not appear to contain CMakeLists.txt").

```powershell
cd C:\Users\<you>\remote-pc-control\windows\unlock-provider   # use your repo's actual path
cmake -B build -A x64
cmake --build build --config Release
signtool sign /fd SHA256 /a build\Release\RemoteUnlockProvider.dll   # or your own signing step
```

> Not sure of your repo's path? From a regular terminal: `dir C:\Users\<you>\remote-pc-control`
> to confirm it's there before switching to the Native Tools shell.

### Step 2 — Register it

As Administrator:

```powershell
.\register.ps1 -DllPath .\build\Release\RemoteUnlockProvider.dll
```

Lock the PC and confirm the normal password tile still works and **no** extra tile appears yet
(correct — nothing is enabled until step 3).

### Step 3 — Enable the feature

Add to `.env`:

```ini
REMOTE_PC_UNLOCK=1
REMOTE_PC_UNLOCK_ACCOUNT=<your Windows username>
REMOTE_PC_UNLOCK_REQUIRE_BIOMETRIC=0
```

Restart the agent. `GET /api/v1/unlock/status` should now report `"integration_installed": true`.

### Step 4 — Enroll your phone

In the app: **Dashboard → Unlock → "Enroll this phone"**. This generates a device key and calls
`POST /api/v1/unlock/devices`. It comes back `PENDING_LOCAL_APPROVAL` — nothing works yet.

### Step 5 — Approve it, on the PC, locally

Deliberately **not** reachable over the network:

```powershell
python -m app.unlock_admin list
python -m app.unlock_admin approve <device-id-or-fingerprint-shown-in-the-app>
```

### Step 6 — Try it

Lock the PC and test both **"Unlock with PIN/Password"** and **"Unlock with Fingerprint"** from
the app.

---

## Revoking a lost phone

```powershell
python -m app.unlock_admin revoke <device-id>
```

on the PC — or `DELETE /api/v1/unlock/devices/{id}` over the authenticated API from another
enrolled, trusted session. Immediately invalidates that device's key; any in-flight challenge for
it is dropped too.

---

## Uninstall / recovery

| Action | Effect |
|---|---|
| Set `REMOTE_PC_UNLOCK=0` (or delete it) in `.env`, restart the agent | Feature stops responding. Provider stays registered and harmless until also removed. |
| `windows\unlock-provider\uninstall.ps1` (as Administrator) | Deletes two registry keys. Never touches your account password, BitLocker, or any other credential provider. |
| Locked out for an unrelated reason | Use Windows' normal recovery path (Safe Mode, a recovery drive, another administrator account) — this feature has no special access that bypasses that. |

Stock Windows sign-in is unaffected the whole time this feature has existed — it only ever
**adds** an extra tile.

---

## Known limitations / what is NOT done here

- ⚠️ **The Windows Credential Provider source is unverified.** It was written against
  Microsoft's documented `ICredentialProvider` / `ICredentialProviderCredential` interfaces for
  `CPUS_UNLOCK_WORKSTATION`, but there was no Windows/MSVC toolchain in the environment that
  produced it, so it has not been compiled, signed, or exercised against a real lock screen.
  **Do not consider Windows unlock functional until you have built it and verified it yourself on
  a disposable Windows 11 VM you can snapshot/roll back**, before ever registering it on a machine
  you depend on.
- Local accounts only for now; Microsoft/domain accounts need a different
  `LogonDomainName`/authentication-package setup in `GetSerialization` that is not implemented.
- One Windows account per PC (`REMOTE_PC_UNLOCK_ACCOUNT`); multi-account selection is not implemented.
- `python -m app.unlock_admin approve` must be run **locally on the PC** — by design, so pairing a
  new phone always needs physical/already-authenticated access to the machine, not just the API token.
- The agent-side rate limiting and challenge store are in-memory and per-process; they reset on restart.
