# Remote PC Control: বাংলা নির্দেশিকা

নিজের Windows PC ফোন থেকে দেখা ও নিয়ন্ত্রণ করার টুল। পূর্ণ ইংরেজি ডকুমেন্টেশন: [README](../README.md)।

> শুধু নিজের PC-তে ব্যবহার করুন। পোর্ট 8888 কখনো সরাসরি ইন্টারনেটে খুলবেন না।

## দ্রুত শুরু

1. PC-তে Python 3.11+ (3.12 সুপারিশকৃত), Node.js 22 ও Git ইনস্টল করুন।
2. PowerShell-এ চালান:
   ```powershell
   git clone https://github.com/mainnetwallet/remote-pc-control.git
   cd remote-pc-control
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\setup.ps1
   ```
   শেষে যে access token দেখাবে সেটা নিরাপদে সেভ করুন।
3. `.\scripts\start.ps1` চালান এবং উইন্ডো খোলা রাখুন।
4. নতুন PowerShell উইন্ডোতে `.\scripts\start-tunnel.ps1` চালান। যে `https://...trycloudflare.com` লিংক আসবে সেটা ফোনে খুলুন (লিংক প্রতিবার বদলায়)।
5. Token দিয়ে **Connect** করে **Start screen** চাপুন। Click / Move / Drag / Scroll মোডে আঙুল দিয়ে mouse চালান।
6. কাজ শেষে tunnel উইন্ডোতে `Ctrl+C` চাপুন। লিংক ও token কাউকে দেবেন না।

নিজের পছন্দের পাসওয়ার্ড দিতে: `.\scripts\set-password.ps1` (কমপক্ষে ৪ অক্ষর, ১২+ হলে ভালো)।

## WebRTC (কম delay)

- ভিডিও UDP-তে সরাসরি ফোন ও PC-র মধ্যে যায় (H.264), তাই delay অনেক কম। Mouse ও keyboard input-ও একই সংযোগের data channel দিয়ে যায়।
- অ্যাপে **Start screen** চাপলে আগে WebRTC চেষ্টা হয়। প্রায় ২০ সেকেন্ডে ভিডিও না এলে অ্যাপ নিজে থেকে পুরোনো WebSocket (JPEG) স্ট্রিমে চলে যায় এবং একটি নোটিশ দেখায়।
- সবচেয়ে ভালো ফল পেতে একই Wi-Fi বা Tailscale ব্যবহার করুন। Cloudflare quick tunnel শুধু TCP বহন করে, তাই শুধু tunnel দিয়ে WebRTC সাধারণত লাগে না।
- মোবাইল ডেটায় না লাগলে TURN সার্ভার দিন (`.env`-এ `REMOTE_PC_TURN_URL`, `REMOTE_PC_TURN_USER`, `REMOTE_PC_TURN_PASS`)।
- বন্ধ করতে `.env`-এ `REMOTE_PC_WEBRTC=0` দিন।
- কোন মোড চলছে বোঝার উপায়: ছবির কোণার লেখা `WebRTC · …` বা `WebSocket · …`।

## আপডেট

`git pull`, তারপর `.\scripts\setup.ps1`, তারপর `.\scripts\start.ps1`। নতুন APK Releases পেজ থেকে ইনস্টল করুন।

## `.env` নতুন করে বানানো

পুরো রিসেট করতে চাইলে আগে backup নিন, কারণ এতে password, Gist ও TURN মান মুছে যায়:

```powershell
Copy-Item .env .env.backup
Copy-Item .env.example .env -Force
.\scripts\set-password.ps1 নতুনPassword
```

এরপর দরকারি মান (`QUICK_TUNNEL`, `GIST_TOKEN`, `GIST_ID`, `REMOTE_PC_TURN_*`) আবার বসান, `start.ps1` রিস্টার্ট করুন এবং শেষে `Remove-Item .env.backup` দিয়ে backup মুছে ফেলুন।

## Cloudflare স্থায়ী লিংক

1. Cloudflare-এ আপনার domain যোগ করুন এবং status **Active** হওয়া পর্যন্ত অপেক্ষা করুন। Domain না থাকলে স্থায়ী লিংক হবে না।
2. Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared > নাম দিন (যেমন `mypc`) > Windows বেছে নিন।
3. Dashboard যে `cloudflared.exe service install <token>` command দেখায়, সেটা **Administrator PowerShell**-এ চালান।
4. Public hostname যোগ করুন: subdomain `pc`, নিজের domain, Type **HTTP**, URL `localhost:8888`।
5. ফোনে `https://pc.আপনার-domain` খুলে token দিন। লিংক আর বদলাবে না এবং PC চালু হলেই tunnel চালু হবে। শুধু `start.ps1` চালু রাখতে হবে।
6. নিরাপত্তার জন্য Access > Applications থেকে শুধু আপনার email-কে অনুমতি দিন। Access চালু থাকলে Android অ্যাপ ব্লক হবে, শুধু browser চলবে।

বিস্তারিত: [CLOUDFLARE.md](CLOUDFLARE.md)।
