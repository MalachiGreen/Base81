"""Tests for CLI interface."""

import pytest
import subprocess
import sys
import os
import tempfile


class TestSelfTest:
    def test_self_test_passes(self):
        result = subprocess.run(
            [sys.executable, "-m", "base81"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(__file__))
        )
        assert result.returncode == 0
        assert "All checks passed" in result.stdout

    def test_self_test_no_errors(self):
        result = subprocess.run(
            [sys.executable, "-m", "base81"],
            capture_output=True,
            text=True
        )
        assert result.stderr == ""


class TestCliEncodeDecode:
    @pytest.fixture
    def test_data(self):
        return b"Hello Base81 World! " * 100

    def test_encode_stdin_stdout(self, test_data):
        result = subprocess.run(
            [sys.executable, "-m", "base81", "encode"],
            input=test_data,
            capture_output=True
        )
        assert result.returncode == 0
        assert len(result.stdout) > 0

    def test_encode_decode_roundtrip(self, test_data):
        encode_result = subprocess.run(
            [sys.executable, "-m", "base81", "encode"],
            input=test_data,
            capture_output=True
        )
        assert encode_result.returncode == 0
        
        decode_result = subprocess.run(
            [sys.executable, "-m", "base81", "decode"],
            input=encode_result.stdout,
            capture_output=True
        )
        assert decode_result.returncode == 0
        assert decode_result.stdout == test_data

    def test_encode_with_line_width(self, test_data):
        result = subprocess.run(
            [sys.executable, "-m", "base81", "encode", "--line-width", "40"],
            input=test_data,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        lines = result.stdout.strip().split('\n')
        assert all(len(line) <= 40 for line in lines)

    def test_decode_with_ignore_ws(self, test_data):
        # First encode with line wrapping
        encode_result = subprocess.run(
            [sys.executable, "-m", "base81", "encode", "--line-width", "40"],
            input=test_data,
            capture_output=True,
            text=True
        )
        
        # Decode with whitespace ignore
        decode_result = subprocess.run(
            [sys.executable, "-m", "base81", "decode", "--ignore-ws"],
            input=encode_result.stdout,
            capture_output=True
        )
        assert decode_result.stdout == test_data

    def test_encode_with_header(self, test_data):
        encode_result = subprocess.run(
            [sys.executable, "-m", "base81", "encode", "--header"],
            input=test_data,
            capture_output=True,
            text=True
        )
        assert encode_result.stdout.startswith("^b81:")

    def test_decode_with_header(self, test_data):
        # Encode with header
        encode_result = subprocess.run(
            [sys.executable, "-m", "base81", "encode", "--header"],
            input=test_data,
            capture_output=True,
            text=True
        )
        
        # Decode with header auto-detection
        decode_result = subprocess.run(
            [sys.executable, "-m", "base81", "decode", "--header"],
            input=encode_result.stdout,
            capture_output=True
        )
        assert decode_result.stdout == test_data

    def test_different_block_sizes(self, test_data):
        for bs in [3, 5, 7]:
            alphabet = "standard" if bs != 5 else "url"
            encode_result = subprocess.run(
                [sys.executable, "-m", "base81", "encode", 
                 "--block-size", str(bs), "--alphabet", alphabet],
                input=test_data,
                capture_output=True
            )
            assert encode_result.returncode == 0
            
            decode_result = subprocess.run(
                [sys.executable, "-m", "base81", "decode",
                 "--block-size", str(bs), "--alphabet", alphabet],
                input=encode_result.stdout,
                capture_output=True
            )
            assert decode_result.stdout == test_data


class TestCliFileOperations:
    @pytest.fixture
    def temp_files(self):
        with tempfile.NamedTemporaryFile(delete=False) as infile:
            infile.write(b"Test data for file operations" * 100)
            infile_path = infile.name
        
        out_path = tempfile.mktemp()
        dec_path = tempfile.mktemp()
        
        yield infile_path, out_path, dec_path
        
        for path in [infile_path, out_path, dec_path]:
            if os.path.exists(path):
                os.unlink(path)

    def test_encode_from_file(self, temp_files):
        infile, outfile, _ = temp_files
        
        result = subprocess.run(
            [sys.executable, "-m", "base81", "encode", 
             "--input", infile, "--output", outfile],
            capture_output=True
        )
        assert result.returncode == 0
        assert os.path.exists(outfile)
        assert os.path.getsize(outfile) > 0

    def test_decode_to_file(self, temp_files):
        infile, outfile, decfile = temp_files
        
        # Encode first
        subprocess.run(
            [sys.executable, "-m", "base81", "encode", 
             "--input", infile, "--output", outfile],
            check=True
        )
        
        # Decode
        result = subprocess.run(
            [sys.executable, "-m", "base81", "decode",
             "--input", outfile, "--output", decfile],
            capture_output=True
        )
        assert result.returncode == 0
        assert os.path.exists(decfile)
        
        # Compare original and decoded
        with open(infile, "rb") as f:
            original = f.read()
        with open(decfile, "rb") as f:
            decoded = f.read()
        assert decoded == original