FROM docker.io/library/golang:1.23-alpine

# git is needed for `go install` to fetch gosec's module graph at build time.
# gcc/musl-dev give `go test -race` a C toolchain — the race detector is
# built on cgo's runtime instrumentation and refuses to run without it
# ("−race requires cgo"), which this Alpine base doesn't ship by default.
RUN apk add --no-cache git gcc musl-dev

# `go build`/`go test` only link the race-detector's cgo shim when
# CGO_ENABLED=1; Alpine's Go image defaults it to 0 for static-binary builds.
ENV CGO_ENABLED=1

# gosec — Go security scanner, the Go analog of Bandit (Python) and
# eslint-plugin-security (TypeScript). Installed at build time (network
# available during `podman build`) so no runtime network access is needed —
# matches the "no calls at runtime" pattern already used for the TS harness.
# GOBIN pinned to a location on PATH regardless of which user runs it.
ENV GOBIN=/usr/local/bin
RUN go install github.com/securego/gosec/v2/cmd/gosec@v2.21.4

# errcheck (unchecked-error gate) and revive (idiomatic-lint gate) -- same
# install-at-build-time/no-runtime-network pattern as gosec above. Both are
# wired into GoRunner.send_pulse() as blocking gates alongside gosec/go vet,
# not advisory-only.
RUN go install github.com/kisielk/errcheck@v1.7.0
RUN go install github.com/mgechev/revive@v1.5.1

# revive.toml drops two purely stylistic default rules (package-comments,
# var-declaration) that have no correctness/security signal and broke known-
# good, already-verified generated code on first use -- see the file itself.
COPY revive.toml /etc/revive.toml

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
