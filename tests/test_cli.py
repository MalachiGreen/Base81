import sys
import pytest
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from base81._cli import main
import base81


def run_cli(args, stdin_data=None):
    """Run CLI with given argument list and optional stdin, return (stdout, stderr, exit_code)."""
    sys.argv = ["base81"] + args
    stdout = StringIO()
    stderr = StringIO()
    exit_code = 0
    # Mock stdin if provided
    if stdin_data is not None:
        import builtins
        original_stdin = sys.stdin
        sys.stdin = StringIO(stdin_data)
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main()
    except SystemExit as e:
        exit_code = e.code if e.code is not None else 0
    finally:
        if stdin_data is not None:
            sys.stdin = original_stdin
    return stdout.getvalue(), stderr.getvalue(), exit_code


def test_cli_self_test():
    # Running with no args runs self-test
    out, err, code = run_cli([])
    assert code == 0
    assert "All checks passed. 🚀" in out


def test_cli_encode_decode_stdin_stdout(tmp_path):
    data = b"Hello CLI"
    # Encode
    out, err, code = run_cli(["encode"], stdin_data=data.decode('latin-1'))
    assert code == 0
    encoded = out.strip()
    # Decode
    out2, err2, code2 = run_cli(["decode"], stdin_data=encoded)
    assert code2 == 0
    assert out2.encode('latin-1') == data


def test_cli_encode_file(tmp_path):
    infile = tmp_path / "input.bin"
    infile.write_bytes(b"File test")
    outfile = tmp_path / "output.b81"
    out, err, code = run_cli(["encode", "-i", str(infile), "-o", str(outfile)])
    assert code == 0
    assert outfile.exists()
    assert outfile.read_text().strip() != ""


def test_cli_decode_file(tmp_path):
    data = b"Decode test"
    enc = base81.encode(data)
    infile = tmp_path / "input.b81"
    infile.write_text(enc)
    outfile = tmp_path / "output.bin"
    out, err, code = run_cli(["decode", "-i", str(infile), "-o", str(outfile)])
    assert code == 0
    assert outfile.read_bytes() == data


def test_cli_header_option(tmp_path):
    infile = tmp_path / "data.bin"
    infile.write_bytes(b"Header test")
    enc_file = tmp_path / "data.b81"
    run_cli(["encode", "--header", "-i", str(infile), "-o", str(enc_file)])
    # Decode with header auto-detection
    out, err, code = run_cli(["decode", "--header", "-i", str(enc_file), "-o", str(tmp_path / "dec.bin")])
    assert code == 0
    assert (tmp_path / "dec.bin").read_bytes() == b"Header test"


def test_cli_dry_run(tmp_path):
    infile = tmp_path / "data.bin"
    infile.write_bytes(b"x" * 1000)
    out, err, code = run_cli(["encode", "--dry-run", "-i", str(infile)])
    assert code == 0
    assert "DRY-RUN" in out
    assert "estimated" in out.lower()


def test_cli_info(tmp_path):
    out, err, code = run_cli(["info"])
    assert code == 0
    assert "Registered codecs:" in out
    assert "standard/3" in out
    # Test info on file
    infile = tmp_path / "test.b81"
    infile.write_text("^b81:7:standard^ABC")
    out, err, code = run_cli(["info", str(infile)])
    assert "header: block_size=7, alphabet=standard" in out


def test_cli_invalid_command():
    out, err, code = run_cli(["unknown"])
    assert code != 0
    assert "error" in err.lower() or "invalid choice" in err


def test_cli_encode_multiple_files(tmp_path):
    # Multiple inputs require output dir
    f1 = tmp_path / "1.bin"
    f1.write_bytes(b"one")
    f2 = tmp_path / "2.bin"
    f2.write_bytes(b"two")
    outdir = tmp_path / "enc"
    outdir.mkdir()
    out, err, code = run_cli(["encode", str(f1), str(f2), "-d", str(outdir)])
    assert code == 0
    assert (outdir / "1.bin.b81").exists()
    assert (outdir / "2.bin.b81").exists()


def test_cli_benchmark():
    out, err, code = run_cli(["encode", "--benchmark", "--block-size", "7"])
    assert code == 0
    assert "Benchmark:" in out
    assert "MB/s" in out