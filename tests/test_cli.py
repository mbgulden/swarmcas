import sys
from unittest.mock import patch
from swarmcas.cli import main

def test_cli_help(capsys):
    with patch.object(sys, 'argv', ['swarmcas', '--help']):
        try:
            main()
        except SystemExit:
            pass
    out, _ = capsys.readouterr()
    assert "Content-addressed immutable artifact and blob store" in out
