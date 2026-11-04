package handler

import (
	"log/slog"
	"math"
	"net/http"
	"net/netip"
	"strconv"
	"strings"
)

// unknownVisitor is the one allowance shared by requests whose address will
// not parse, so a malformed header fails closed rather than unlimited.
const unknownVisitor = "unknown"

// fromAnotherSite reports a browser request made from another site's page,
// such as an image tag or a script elsewhere pointed at the API. Browsers set
// Sec-Fetch-Site and pages cannot change it. "none" is a URL the user opened
// themselves; no header at all is a non-browser client, which the
// per-visitor limit covers instead.
func fromAnotherSite(secFetchSite string) bool {
	switch secFetchSite {
	case "", "same-origin", "none":
		return false
	}
	return true
}

// refuseOtherSite answers 403 to a request from another site's page and
// reports whether it did.
func refuseOtherSite(w http.ResponseWriter, r *http.Request, word string) bool {
	site := r.Header.Get("Sec-Fetch-Site")
	if !fromAnotherSite(site) {
		return false
	}
	slog.Warn("forest: refused a request from another site", "word", word, "sec_fetch_site", site)
	writeForestError(w, http.StatusForbidden, "new metaphor forests can only be requested from this site")
	return true
}

// visitorKey names who a request is from, for the per-visitor limit, or
// reports exempt for a call made on this host (the enricher, a deploy
// check). The API listens on loopback behind Caddy, which sets
// X-Forwarded-For on every request it proxies and, with no trusted_proxies,
// replaces whatever the client sent; its entry is the last one. IPv6
// visitors are grouped by /64, the block one subscriber is given.
func visitorKey(r *http.Request) (key string, exempt bool) {
	if isDirectLoopback(r) {
		return "", true
	}
	addr, err := netip.ParseAddrPort(r.RemoteAddr)
	if err != nil {
		return unknownVisitor, false
	}
	client := addr.Addr().Unmap()
	if client.IsLoopback() {
		forwarded, ok := lastForwardedFor(r)
		if !ok {
			return unknownVisitor, false
		}
		client = forwarded
	}
	if client.Is6() {
		block, err := client.Prefix(64)
		if err != nil {
			return unknownVisitor, false
		}
		return block.String(), false
	}
	return client.String(), false
}

// lastForwardedFor parses the last X-Forwarded-For entry, with or without a
// port.
func lastForwardedFor(r *http.Request) (netip.Addr, bool) {
	values := r.Header.Values("X-Forwarded-For")
	if len(values) == 0 {
		return netip.Addr{}, false
	}
	entries := strings.Split(values[len(values)-1], ",")
	last := strings.TrimSpace(entries[len(entries)-1])
	if a, err := netip.ParseAddr(last); err == nil {
		return a.Unmap(), true
	}
	if ap, err := netip.ParseAddrPort(last); err == nil {
		return ap.Addr().Unmap(), true
	}
	return netip.Addr{}, false
}

// admitVisitor spends one of the visitor's forests, or answers 429 and
// reports false. The refund gives the forest back when the request is
// refused further on, so only generated forests count.
func (h *ForestHandler) admitVisitor(w http.ResponseWriter, r *http.Request, word string) (refund func(), ok bool) {
	noop := func() {}
	if h.Visitors == nil {
		return noop, true
	}
	key, exempt := visitorKey(r)
	if exempt {
		return noop, true
	}
	refund, wait, ok := h.Visitors.Take(key)
	if !ok {
		secs := max(1, int(math.Ceil(wait.Seconds())))
		slog.Warn("forest: visitor limit reached", "word", word, "visitor", key, "retry_after_s", secs)
		w.Header().Set("Retry-After", strconv.Itoa(secs))
		writeForestError(w, http.StatusTooManyRequests, "too many new metaphor forests from this address, try again later")
		return nil, false
	}
	return refund, true
}
