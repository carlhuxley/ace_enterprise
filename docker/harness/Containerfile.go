FROM docker.io/library/golang:1.23-alpine

# git is needed for `go install` to fetch gosec's module graph at build time.
RUN apk add --no-cache git

# gosec — Go security scanner, the Go analog of Bandit (Python) and
# eslint-plugin-security (TypeScript). Installed at build time (network
# available during `podman build`) so no runtime network access is needed —
# matches the "no calls at runtime" pattern already used for the TS harness.
# GOBIN pinned to a location on PATH regardless of which user runs it.
ENV GOBIN=/usr/local/bin
RUN go install github.com/securego/gosec/v2/cmd/gosec@v2.21.4

# Non-root runner user (matches Containerfile.ts's hardening — the Python
# harness is the one exception, tracked separately).
RUN addgroup -S ace && adduser -S ace -G ace

# Workspace bind-mounted here by the runner (read-only at runtime).
RUN mkdir -p /workspace && chown ace:ace /workspace

# /tmp is mounted as tmpfs by the runner (gofmt output, go build cache).
ENV GOCACHE=/tmp/go-build-cache
ENV GOPATH=/tmp/go-path

# This harness runs with --network none by design. Without telling the go
# toolchain that up front, `go test`/`go vet` try to reach the module proxy
# and checksum database for verification, and a blocked network call hangs
# (slow DNS/connect failure) rather than failing fast — discovered live,
# tests timed out instead of erroring. GOFLAGS=-mod=mod avoids readonly-mod
# errors on a workspace that never has a prior go.sum.
ENV GOPROXY=off
ENV GOSUMDB=off
ENV GOFLAGS=-mod=mod

USER ace
WORKDIR /workspace
