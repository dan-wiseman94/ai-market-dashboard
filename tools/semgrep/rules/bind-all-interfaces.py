# Test fixture for bind-all-interfaces-python. Run: semgrep --test --config <dir>
def _fixture(sock, cfg):
    # literals assigned to attributes (no local reuse, so constant-propagation can't
    # re-flag them on a later line — which is correct behaviour, just awkward to unit-test)
    # ruleid: bind-all-interfaces-python
    cfg.host = "0.0.0.0"
    # ruleid: bind-all-interfaces-python
    sock.bind(("0.0.0.0", 8000))
    # ok: bind-all-interfaces-python
    cfg.safe = "127.0.0.1"
    # ok: bind-all-interfaces-python
    cfg.other = "0.0.0.0.0"
