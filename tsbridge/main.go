// tsbridge: a tiny Tailscale node that lives inside Remote PC Control, so Tailscale does not have to be installed on
// the PC. It joins the user's tailnet in userspace (no driver, no virtual network card, no admin rights needed) and
// forwards every connection that arrives on <tailnet-ip>:<port> to the agent on 127.0.0.1:<port>.
//
// The panel API is meant for this PC only. The agent decides that from the peer address, which would be 127.0.0.1 for
// forwarded traffic too, so every forwarded request carries X-Forwarded-For and Cf-Connecting-Ip (the real tailnet
// address, always overwritten here). The agent refuses the panel API for requests that have those headers.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"time"

	"tailscale.com/tsnet"
)

type status struct {
	State   string   `json:"state"`    // NoState, NeedsLogin, Starting, Running, ...
	AuthURL string   `json:"auth_url"` // open this once to sign in
	IPs     []string `json:"ips"`
	Name    string   `json:"name"`
	Error   string   `json:"error"`
	Updated int64    `json:"updated"`
}

func writeStatus(path string, s status) {
	s.Updated = time.Now().Unix()
	b, _ := json.Marshal(s)
	tmp := path + ".tmp"
	if os.WriteFile(tmp, b, 0o600) == nil {
		_ = os.Rename(tmp, path)
	}
}

func main() {
	stateDir := flag.String("state", "", "folder for the Tailscale login state")
	statusFile := flag.String("status", "", "file the status is written to (JSON)")
	port := flag.Int("port", 8888, "agent port (same number is opened on the tailnet)")
	host := flag.String("hostname", "remote-pc", "device name in the tailnet")
	flag.Parse()
	if *stateDir == "" || *statusFile == "" {
		log.Fatal("usage: tsbridge -state DIR -status FILE [-port 8888] [-hostname NAME]")
	}
	if err := os.MkdirAll(*stateDir, 0o700); err != nil {
		log.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(*statusFile), 0o700); err != nil {
		log.Fatal(err)
	}

	// The app starts us with a pipe on stdin: when the app is gone the pipe closes and we leave too.
	go func() { _, _ = io.Copy(io.Discard, os.Stdin); os.Exit(0) }()

	srv := &tsnet.Server{Dir: *stateDir, Hostname: *host, UserLogf: log.Printf, Logf: func(string, ...any) {}}
	defer srv.Close()
	if err := srv.Start(); err != nil {
		writeStatus(*statusFile, status{State: "Error", Error: err.Error()})
		log.Fatal(err)
	}
	lc, err := srv.LocalClient()
	if err != nil {
		writeStatus(*statusFile, status{State: "Error", Error: err.Error()})
		log.Fatal(err)
	}

	go func() {
		for {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			st, err := lc.Status(ctx)
			cancel()
			if err != nil {
				writeStatus(*statusFile, status{State: "Starting", Error: err.Error()})
			} else {
				s := status{State: st.BackendState, AuthURL: st.AuthURL}
				for _, ip := range st.TailscaleIPs {
					s.IPs = append(s.IPs, ip.String())
				}
				if st.Self != nil {
					s.Name = st.Self.DNSName
				}
				writeStatus(*statusFile, s)
			}
			time.Sleep(2 * time.Second)
		}
	}()

	// Wait until signed in (the user opens auth_url once; the login is then kept in the state folder).
	upCtx, upCancel := context.WithTimeout(context.Background(), 24*time.Hour)
	defer upCancel()
	if _, err := srv.Up(upCtx); err != nil {
		writeStatus(*statusFile, status{State: "Error", Error: err.Error()})
		log.Fatal(err)
	}

	ln, err := srv.Listen("tcp", fmt.Sprintf(":%d", *port))
	if err != nil {
		writeStatus(*statusFile, status{State: "Error", Error: err.Error()})
		log.Fatal(err)
	}
	target, _ := url.Parse(fmt.Sprintf("http://127.0.0.1:%d", *port))
	proxy := &httputil.ReverseProxy{
		Rewrite: func(r *httputil.ProxyRequest) {
			r.SetURL(target)
			r.SetXForwarded() // X-Forwarded-For: makes the agent treat this as remote traffic
			peer, _, _ := net.SplitHostPort(r.In.RemoteAddr)
			r.Out.Header.Set("Cf-Connecting-Ip", peer) // per-client lockout; always overwritten, never taken from the phone
		},
		FlushInterval: -1, // stream the screen frames at once
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, err error) {
			http.Error(w, "the agent does not answer: "+err.Error(), http.StatusBadGateway)
		},
	}
	log.Fatal((&http.Server{Handler: proxy}).Serve(ln))
}
