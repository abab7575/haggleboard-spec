import contextlib, io, re, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
import haggle_demo

# Private values: seller floors (185, 1120) and shopper ceilings (205, 1180).
FORBIDDEN = ("185", "1120", "205", "1180")

def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): haggle_demo.main(argv)
    return buf.getvalue()

def assert_public_safe(text):
    assert not re.search(r"floor|ceiling", text, re.I), "mentions a floor or ceiling"
    for v in FORBIDDEN:
        # word boundaries so random hex in hashes/nonces cannot match
        assert not re.search(rf"(?<![0-9A-Za-z.]){v}(?![0-9A-Za-z])", text), f"private value {v} leaked"

def test_recording_never_prints_floors_or_ceilings():
    assert_public_safe(run(["--recording"]))

def test_sample_transcript_is_public_safe():
    assert_public_safe((ROOT / "demo" / "sample_transcript.txt").read_text())

def test_sample_transcript_matches_recording_shape():
    sample = (ROOT / "demo" / "sample_transcript.txt").read_text().splitlines()
    out = run(["--recording"]).splitlines()
    assert len(sample) == len(out)
    strip = lambda l: re.sub(r"[0-9a-f]{6,}|\d\d:\d\d:\d\d", "", l)
    assert [strip(l) for l in sample] == [strip(l) for l in out]

def test_default_mode_is_dev_only_and_shows_floors():
    assert "floor EUR 185" in run([])
