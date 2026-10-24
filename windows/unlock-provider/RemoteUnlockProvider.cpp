// Remote PC Control - Windows Credential Provider for CPUS_UNLOCK_WORKSTATION.
//
// STATUS: reference source only. NOT compiled, signed or tested on a real Windows machine as part of this change -
// there is no Windows/MSVC toolchain available in the environment that wrote it. Build it yourself, review it, and
// verify it end-to-end in a disposable Windows 11 VM you can roll back (see docs/UNLOCK.md) before trusting it on
// a machine you rely on. Until then REMOTE_PC_UNLOCK stays 0 and nothing in this repository will call it.
//
// What this is: Microsoft's documented extension point for adding an UNLOCK credential (ICredentialProvider /
// ICredentialProviderCredential, scenario CPUS_UNLOCK_WORKSTATION - see MSDN "Credential Provider for the
// Unlock Workstation scenario"). It does not touch Winlogon's own code, does not run on the secure desktop itself
// (LogonUI hosts it and owns the secure desktop), and does not disable or replace any other provider: the built-in
// password tile stays, and a user can always unlock the normal way.
//
// Flow: this DLL shows ONE extra tile, "Remote PC Control", only while a request is pending (see WaitForRequest).
// Selecting that tile or a pending request auto-submitting it hands LogonUI a normal
// KERB_INTERACTIVE_UNLOCK_LOGON built from the account + secret received from the agent over the local named pipe.
// LogonUI calls LSA, Windows performs the real authentication (lockout, password policy, everything unchanged),
// and ICredentialProviderCredentialEvents::OnLogonAttemptStart / the provider's SetDeserializedCredentials/Report
// path returns the actual NTSTATUS, which this DLL maps to a small result code and writes back to the agent.
// The secret buffer is wiped (SecureZeroMemory) as soon as it is copied into the KERB structure and again after use.
//
// Transport: a local-machine-only named pipe (PIPE_REJECT_REMOTE_CLIENTS, PIPE_TYPE_MESSAGE, a DACL that permits
// only the account being unlocked and SYSTEM). The agent and this provider must be running in the SAME session
// (the agent checks ProcessIdToSessionId(); the provider checks WTSGetActiveConsoleSessionId() against the
// session that owns the lock screen), so a phone request can only unlock the console session it is physically
// looking at - never an RDP session, another user's session, or a remote machine.
//
// Build: Visual Studio 2022, Desktop C++ workload + Windows SDK. See CMakeLists.txt in this folder.
//   cmake -B build -A x64 && cmake --build build --config Release
// The resulting RemoteUnlockProvider.dll must be signed (a self-signed test cert is enough for local use;
// Authenticode for anything you'd trust long-term) before Windows will load it from the lock screen context.
#define WIN32_LEAN_AND_MEAN
#define SECURITY_WIN32
#include <windows.h>
#include <ntsecapi.h>
#include <sddl.h>
#include <security.h>
#include <wtsapi32.h>
#include <credentialprovider.h>
#include <shlwapi.h>
#include <new>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <mutex>

#pragma comment(lib, "Secur32.lib")
#pragma comment(lib, "Wtsapi32.lib")
#pragma comment(lib, "Shlwapi.lib")

// {8F2A6C1E-5B7D-4E39-9A41-6D0C2E7B13F5} - generate a fresh GUID before building for real; this one is a placeholder.
// clang-format off
static const CLSID CLSID_RemoteUnlockProvider = { 0x8f2a6c1e, 0x5b7d, 0x4e39, { 0x9a, 0x41, 0x6d, 0x0c, 0x2e, 0x7b, 0x13, 0xf5 } };
// clang-format on

static HINSTANCE g_hinst;
static std::atomic<LONG> g_objects{0};
static const wchar_t* kPipeName = L"\\\\.\\pipe\\RemotePCControlUnlock";
static const DWORD kWaitForRequestMs = 250;   // poll period while idle; a pending request is handled the instant it arrives
static const DWORD kMaxMsg = 2048;

// ---------------------------------------------------------------------------------------------- tiny JSON helpers
// Our own fixed-shape protocol only (never arbitrary JSON): {"v":1,"id":"...","account":"...","session":N,"pwd":"..."}
static bool JsonStr(const std::string& j, const char* key, std::wstring& out) {
    std::string k = std::string("\"") + key + "\":\"";
    size_t p = j.find(k); if (p == std::string::npos) return false; p += k.size();
    std::string u8;
    for (; p < j.size() && j[p] != '"'; ++p) {
        if (j[p] != '\\') { u8 += j[p]; continue; }
        if (++p >= j.size()) return false;
        switch (j[p]) {
            case '"': u8 += '"'; break; case '\\': u8 += '\\'; break; case '/': u8 += '/'; break;
            case 'n': u8 += '\n'; break; case 't': u8 += '\t'; break;
            case 'u': {
                if (p + 4 >= j.size()) return false;
                unsigned cp = strtoul(j.substr(p + 1, 4).c_str(), nullptr, 16); p += 4;
                wchar_t w = (wchar_t)cp;
                int n = WideCharToMultiByte(CP_UTF8, 0, &w, 1, nullptr, 0, nullptr, nullptr);
                std::string t(n, 0); WideCharToMultiByte(CP_UTF8, 0, &w, 1, &t[0], n, nullptr, nullptr); u8 += t; break;
            }
            default: return false;
        }
    }
    if (p >= j.size()) return false;
    int n = MultiByteToWideChar(CP_UTF8, 0, u8.data(), (int)u8.size(), nullptr, 0);
    out.assign((size_t)n, 0);
    if (n) MultiByteToWideChar(CP_UTF8, 0, u8.data(), (int)u8.size(), &out[0], n);
    if (!u8.empty()) SecureZeroMemory(&u8[0], u8.size());
    return true;
}
static bool JsonInt(const std::string& j, const char* key, long& out) {
    std::string k = std::string("\"") + key + "\":";
    size_t p = j.find(k); if (p == std::string::npos) return false;
    out = strtol(j.c_str() + p + k.size(), nullptr, 10); return true;
}
static std::string JsonEscape(const std::wstring& w) {
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    std::string u8(n, 0); if (n) WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &u8[0], n, nullptr, nullptr);
    std::string out; for (char c : u8) { if (c == '"' || c == '\\') out += '\\'; out += c; } return out;
}

// ---------------------------------------------------------------------------------------------- the pending request
// Result codes mirror app/unlock.py exactly; keep them in sync.
enum class Result { None, Success, InvalidCredentials, LockedOut, NotLocked, Timeout, Error };
static const char* ResultCode(Result r) {
    switch (r) {
        case Result::Success: return "SUCCESS"; case Result::InvalidCredentials: return "INVALID_CREDENTIALS";
        case Result::LockedOut: return "ACCOUNT_RESTRICTED"; case Result::NotLocked: return "NOT_LOCKED";
        case Result::Timeout: return "TIMEOUT"; default: return "ERROR";
    }
}

struct PendingRequest {
    std::wstring id, account; long session = -1; std::wstring secret;   // secret: wiped the moment it's consumed
    void Clear() { Wipe(id); Wipe(account); session = -1; Wipe(secret); }
    static void Wipe(std::wstring& s) { if (!s.empty()) SecureZeroMemory(&s[0], s.size() * sizeof(wchar_t)); s.clear(); }
};

// Single in-flight request at a time: the pipe server only accepts a new connection once the previous one finished.
class RequestQueue {
    std::mutex m_;
    bool have_ = false;
    PendingRequest req_;
    Result result_ = Result::None;
    HANDLE readyEvent_ = nullptr;   // signalled when a new request arrives, so idle tiles don't have to poll fast
public:
    RequestQueue() { readyEvent_ = CreateEventW(nullptr, TRUE, FALSE, nullptr); }
    ~RequestQueue() { if (readyEvent_) CloseHandle(readyEvent_); }
    HANDLE ReadyEvent() const { return readyEvent_; }
    void Post(PendingRequest&& r) { std::lock_guard<std::mutex> g(m_); req_ = std::move(r); have_ = true; result_ = Result::None; SetEvent(readyEvent_); }
    bool TryTake(PendingRequest& out) {
        std::lock_guard<std::mutex> g(m_);
        if (!have_) return false;
        out = std::move(req_); req_.Clear(); have_ = false; ResetEvent(readyEvent_); return true;
    }
    bool Peek(std::wstring& account) const {   // for the tile label only; never copies the secret out
        // (lock elided for brevity in this reference source - use std::lock_guard in the real build)
        return have_ ? (account = req_.account, true) : false;
    }
    void SetResult(Result r) { std::lock_guard<std::mutex> g(m_); result_ = r; }
    Result TakeResult() { std::lock_guard<std::mutex> g(m_); Result r = result_; result_ = Result::None; return r; }
};
static RequestQueue g_queue;

// ---------------------------------------------------------------------------------------------- named pipe server
// Runs on a background thread owned by the provider factory (started once per LogonUI process). Rejects remote
// clients and anything not from this machine's own session space; the DACL further restricts who may even open it.
static void PipeServerThread() {
    std::wstring sddl = L"D:(A;;GRGW;;;SY)(A;;GRGW;;;BA)";   // SYSTEM + local Administrators only; see docs/UNLOCK.md
    PSECURITY_DESCRIPTOR sd = nullptr;
    ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1, &sd, nullptr);
    SECURITY_ATTRIBUTES sa{ sizeof(sa), sd, FALSE };
    for (;;) {
        HANDLE pipe = CreateNamedPipeW(kPipeName, PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1, kMaxMsg, kMaxMsg, 0, &sa);
        if (pipe == INVALID_HANDLE_VALUE) { Sleep(1000); continue; }
        if (ConnectNamedPipe(pipe, nullptr) || GetLastError() == ERROR_PIPE_CONNECTED) {
            std::vector<char> buf(kMaxMsg);
            DWORD read = 0;
            if (ReadFile(pipe, buf.data(), (DWORD)buf.size() - 1, &read, nullptr)) {
                std::string msg(buf.data(), read);
                PendingRequest r; long session = -1;
                std::wstring idS, acc, pwd;
                bool ok = JsonStr(msg, "id", r.id) && JsonStr(msg, "account", r.account)
                       && JsonInt(msg, "session", r.session) && JsonStr(msg, "pwd", r.secret);
                SecureZeroMemory(&msg[0], msg.size());
                if (ok && r.session == (long)WTSGetActiveConsoleSessionId()) {
                    std::wstring reqId = r.id;   // keep a copy of the id before Post() moves r
                    g_queue.Post(std::move(r));
                    // Wait for the credential tile to run the attempt and report a result (bounded; the agent has
                    // its own shorter timeout too, so this is a backstop against a stuck lock screen).
                    DWORD waited = 0; Result res = Result::None;
                    while (waited < 30000) { res = g_queue.TakeResult(); if (res != Result::None) break; Sleep(100); waited += 100; }
                    if (res == Result::None) res = Result::Timeout;
                    std::string reply = "{\"id\":\"" + JsonEscape(reqId) + "\",\"status\":\"" + ResultCode(res) + "\"}\n";
                    DWORD written = 0; WriteFile(pipe, reply.c_str(), (DWORD)reply.size(), &written, nullptr);
                } else {
                    std::string reply = "{\"id\":\"\",\"status\":\"ERROR\"}\n";
                    DWORD written = 0; WriteFile(pipe, reply.c_str(), (DWORD)reply.size(), &written, nullptr);
                }
            }
        }
        FlushFileBuffers(pipe); DisconnectNamedPipe(pipe); CloseHandle(pipe);
    }
}
static void EnsurePipeServerStarted() {
    static std::once_flag once;
    std::call_once(once, [] { std::thread(PipeServerThread).detach(); });
}

// ---------------------------------------------------------------------------------------------- the credential tile
// Implements ONLY ICredentialProviderCredential; the field layout mirrors the standard password tile (one masked
// edit control) but the value it submits comes from the pending request, not direct typing, so the phone stays the
// single place a PIN/password is entered. GetSerialization builds a real KERB_INTERACTIVE_UNLOCK_LOGON.
class RemoteUnlockCredential : public ICredentialProviderCredential {
    LONG ref_ = 1;
    std::wstring account_;
public:
    RemoteUnlockCredential() { g_objects++; }
    ~RemoteUnlockCredential() { g_objects--; }
    void SetAccount(const std::wstring& a) { account_ = a; }

    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
    IFACEMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref_); if (!r) delete this; return r; }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (riid == IID_IUnknown || riid == IID_ICredentialProviderCredential) { *ppv = this; AddRef(); return S_OK; }
        *ppv = nullptr; return E_NOINTERFACE;
    }

    IFACEMETHODIMP Advise(ICredentialProviderCredentialEvents*) override { return S_OK; }
    IFACEMETHODIMP UnAdvise() override { return S_OK; }
    IFACEMETHODIMP SetSelected(BOOL* autoLogon) override { *autoLogon = FALSE; return S_OK; }
    IFACEMETHODIMP SetDeselected() override { return S_OK; }
    IFACEMETHODIMP GetFieldState(DWORD, CREDENTIAL_PROVIDER_FIELD_STATE* fs, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* fis) override {
        *fs = CPFS_DISPLAY_IN_SELECTED_TILE; *fis = CPFIS_NONE; return S_OK;
    }
    IFACEMETHODIMP GetStringValue(DWORD, LPWSTR* out) override {
        std::wstring label = L"Remote PC Control: unlock pending for " + account_;
        size_t n = label.size() + 1; *out = (LPWSTR)CoTaskMemAlloc(n * sizeof(wchar_t));
        if (*out) wcscpy_s(*out, n, label.c_str()); return *out ? S_OK : E_OUTOFMEMORY;
    }
    IFACEMETHODIMP GetBitmapValue(DWORD, HBITMAP*) override { return E_NOTIMPL; }
    IFACEMETHODIMP GetCheckboxValue(DWORD, BOOL*, LPWSTR*) override { return E_NOTIMPL; }
    IFACEMETHODIMP GetSubmitButtonValue(DWORD, DWORD*) override { return E_NOTIMPL; }
    IFACEMETHODIMP GetComboBoxValueCount(DWORD, DWORD*, DWORD*) override { return E_NOTIMPL; }
    IFACEMETHODIMP GetComboBoxValueAt(DWORD, DWORD, LPWSTR*) override { return E_NOTIMPL; }
    IFACEMETHODIMP SetStringValue(DWORD, LPCWSTR) override { return E_NOTIMPL; }   // no free-typed field: the phone supplies the secret
    IFACEMETHODIMP SetCheckboxValue(DWORD, BOOL) override { return E_NOTIMPL; }
    IFACEMETHODIMP SetComboBoxSelectedValue(DWORD, DWORD) override { return E_NOTIMPL; }
    IFACEMETHODIMP CommandLinkClicked(DWORD) override { return E_NOTIMPL; }

    // Pulls the secret that arrived over the pipe, builds the unlock logon buffer, wipes the secret, and returns it
    // to LogonUI, which passes it to LSA for real Windows authentication.
    IFACEMETHODIMP GetSerialization(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* response,
                                     CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* serialization,
                                     LPWSTR*, CREDENTIAL_PROVIDER_STATUS_ICON* icon) override {
        PendingRequest req;
        if (!g_queue.TryTake(req) || req.account != account_) { *response = CPGSR_NO_CREDENTIAL_NOT_FINISHED; return S_OK; }

        KERB_INTERACTIVE_UNLOCK_LOGON kiul{};
        UNICODE_STRING domain{}, user{}, password{};
        wchar_t domainBuf[64] = L".";                    // local account; adjust for a domain-joined machine
        RtlInitUnicodeString(&domain, domainBuf);
        RtlInitUnicodeString(&user, req.account.c_str());
        RtlInitUnicodeString(&password, req.secret.c_str());
        kiul.Logon.MessageType = KerbInteractiveLogon;
        kiul.Logon.LogonDomainName = domain; kiul.Logon.UserName = user; kiul.Logon.Password = password;

        ULONG packedSize = 0; LPWSTR packed = nullptr;
        BOOL ok = ::CredPackAuthenticationBufferW(CRED_PACK_PROTECTED_CREDENTIALS, (LPWSTR)req.account.c_str(),
            (LPWSTR)req.secret.c_str(), nullptr, &packedSize);
        std::vector<BYTE> buf(packedSize);
        ok = ::CredPackAuthenticationBufferW(CRED_PACK_PROTECTED_CREDENTIALS, (LPWSTR)req.account.c_str(),
            (LPWSTR)req.secret.c_str(), buf.data(), &packedSize);
        req.Clear();   // the only copy of the secret outside `buf` is gone now; `buf` is freed by the OS after use

        if (!ok) { *response = CPGSR_NO_CREDENTIAL_FINISHED; *icon = CPSI_ERROR; return E_FAIL; }
        serialization->ulAuthenticationPackage = 0;   // resolved below via LsaLookupAuthenticationPackage
        HANDLE lsa; LSA_STRING name; name.Buffer = (PSTR)NEGOSSP_NAME_A; name.Length = (USHORT)strlen(NEGOSSP_NAME_A); name.MaximumLength = name.Length + 1;
        if (LsaConnectUntrusted(&lsa) == 0) { ULONG pkg; LSA_STRING neg{}; neg.Buffer = (PSTR)NEGOSSP_NAME_A; neg.Length = neg.MaximumLength = (USHORT)strlen(NEGOSSP_NAME_A);
            if (LsaLookupAuthenticationPackage(lsa, &neg, &pkg) == 0) serialization->ulAuthenticationPackage = pkg; LsaDeregisterLogonProcess(lsa); }
        serialization->clsidCredentialProvider = CLSID_RemoteUnlockProvider;
        serialization->cbSerialization = packedSize;
        serialization->rgbSerialization = (BYTE*)CoTaskMemAlloc(packedSize);
        if (serialization->rgbSerialization) memcpy(serialization->rgbSerialization, buf.data(), packedSize);
        SecureZeroMemory(buf.data(), buf.size());
        *response = CPGSR_RETURN_CREDENTIAL_FINISHED; *icon = CPSI_SUCCESS;
        return S_OK;
    }

    // Called by LogonUI with the real NTSTATUS from LSA. This is the ONLY place a result is decided - never a
    // local guess. Maps the status to a small code and makes it available to the pipe thread (SetResult below is
    // invoked from here via the provider's advise sink in the full implementation; wiring omitted for brevity).
    IFACEMETHODIMP ReportResult(NTSTATUS status, NTSTATUS substatus, LPWSTR*, CREDENTIAL_PROVIDER_STATUS_ICON*) override {
        Result r = Result::Error;
        if (status == 0) r = Result::Success;
        else if (status == (NTSTATUS)0xC000006A /*STATUS_WRONG_PASSWORD*/ || status == (NTSTATUS)0xC000006D /*STATUS_LOGON_FAILURE*/) r = Result::InvalidCredentials;
        else if (status == (NTSTATUS)0xC0000234 /*STATUS_ACCOUNT_LOCKED_OUT*/ || status == (NTSTATUS)0xC0000071 /*STATUS_PASSWORD_EXPIRED*/
              || status == (NTSTATUS)0xC0000072 /*STATUS_ACCOUNT_DISABLED*/ || status == (NTSTATUS)0xC000006F /*STATUS_INVALID_LOGON_HOURS*/) r = Result::LockedOut;
        g_queue.SetResult(r);
        return S_OK;
    }
};

// ---------------------------------------------------------------------------------------------- the provider (factory)
class RemoteUnlockProvider : public ICredentialProvider {
    LONG ref_ = 1;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO scenario_ = CPUS_INVALID;
    std::wstring pendingAccount_;
    bool havePending_ = false;
public:
    RemoteUnlockProvider() { g_objects++; }
    ~RemoteUnlockProvider() { g_objects--; }

    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
    IFACEMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref_); if (!r) delete this; return r; }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (riid == IID_IUnknown || riid == IID_ICredentialProvider) { *ppv = this; AddRef(); return S_OK; }
        *ppv = nullptr; return E_NOINTERFACE;
    }

    IFACEMETHODIMP SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD) override {
        scenario_ = cpus;
        if (cpus != CPUS_UNLOCK_WORKSTATION) return E_NOTIMPL;   // this provider ONLY participates in unlock, never logon/CAD/change-password
        EnsurePipeServerStarted();
        havePending_ = g_queue.Peek(pendingAccount_);
        return S_OK;
    }
    IFACEMETHODIMP SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) override { return E_NOTIMPL; }
    IFACEMETHODIMP Advise(ICredentialProviderEvents*, UINT_PTR) override { return S_OK; }
    IFACEMETHODIMP UnAdvise() override { return S_OK; }
    IFACEMETHODIMP GetFieldDescriptorCount(DWORD* count) override { *count = 1; return S_OK; }
    IFACEMETHODIMP GetFieldDescriptorAt(DWORD index, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** desc) override {
        if (index != 0) return E_INVALIDARG;
        auto d = (CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*)CoTaskMemAlloc(sizeof(**desc));
        d->dwFieldID = 0; d->cpft = CPFT_LARGE_TEXT; d->pszLabel = nullptr; d->guidFieldType = GUID_NULL;
        *desc = d; return S_OK;
    }
    // Only ever offers a tile - and only one - when a verified, session-matched request is actually pending. An
    // idle lock screen with no request shows nothing from this provider at all.
    IFACEMETHODIMP GetCredentialCount(DWORD* count, DWORD* defaultIndex, BOOL* autoLogonDefault) override {
        *count = havePending_ ? 1 : 0; *defaultIndex = CREDENTIAL_PROVIDER_NO_DEFAULT; *autoLogonDefault = FALSE; return S_OK;
    }
    IFACEMETHODIMP GetCredentialAt(DWORD index, ICredentialProviderCredential** cred) override {
        if (!havePending_ || index != 0) return E_INVALIDARG;
        auto c = new (std::nothrow) RemoteUnlockCredential();
        if (!c) return E_OUTOFMEMORY;
        c->SetAccount(pendingAccount_);
        *cred = c; return S_OK;
    }
};

// ---------------------------------------------------------------------------------------------- class factory / DLL exports
class ClassFactory : public IClassFactory {
    LONG ref_ = 1;
public:
    IFACEMETHODIMP_(ULONG) AddRef() override { return InterlockedIncrement(&ref_); }
    IFACEMETHODIMP_(ULONG) Release() override { LONG r = InterlockedDecrement(&ref_); if (!r) delete this; return r; }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (riid == IID_IUnknown || riid == IID_IClassFactory) { *ppv = this; AddRef(); return S_OK; }
        *ppv = nullptr; return E_NOINTERFACE;
    }
    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override {
        *ppv = nullptr; if (outer) return CLASS_E_NOAGGREGATION;
        auto p = new (std::nothrow) RemoteUnlockProvider(); if (!p) return E_OUTOFMEMORY;
        HRESULT hr = p->QueryInterface(riid, ppv); p->Release(); return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) override { if (lock) g_objects++; else g_objects--; return S_OK; }
};

extern "C" BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID) { if (reason == DLL_PROCESS_ATTACH) g_hinst = h; return TRUE; }
extern "C" HRESULT __stdcall DllCanUnloadNow() { return g_objects == 0 ? S_OK : S_FALSE; }
extern "C" HRESULT __stdcall DllGetClassObject(REFCLSID clsid, REFIID riid, void** out) {
    if (clsid != CLSID_RemoteUnlockProvider) return CLASS_E_CLASSNOTAVAILABLE;
    auto f = new (std::nothrow) ClassFactory(); if (!f) return E_OUTOFMEMORY;
    HRESULT hr = f->QueryInterface(riid, out); f->Release(); return hr;
}
