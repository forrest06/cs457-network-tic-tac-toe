"""Tests for required command-line flags and port validation."""

import socket
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import client
import server


class CommandLineTests(unittest.TestCase):
    def test_client_requires_host_and_port(self) -> None:
        with self.assertRaises(SystemExit):
            client.build_parser().parse_args([])

        args = client.build_parser().parse_args(
            ["-i", "server.fisher.edu", "-p", "45700"]
        )
        self.assertEqual(args.hostname, "server.fisher.edu")
        self.assertEqual(args.port, 45700)

    def test_server_requires_port(self) -> None:
        with self.assertRaises(SystemExit):
            server.build_parser().parse_args([])

        args = server.build_parser().parse_args(["-p", "45700"])
        self.assertEqual(args.port, 45700)

    def test_port_range_is_enforced(self) -> None:
        for invalid_port in ("80", "65536", "not-a-number"):
            with self.assertRaises(SystemExit):
                client.build_parser().parse_args(
                    ["-i", "localhost", "-p", invalid_port]
                )

    def test_dns_failure_is_friendly_and_returns_one(self) -> None:
        output = StringIO()
        with patch("client.socket.gethostbyname", side_effect=socket.gaierror):
            with redirect_stdout(output):
                result = client.main(
                    ["-i", "missing.invalid", "-p", "45700", "-n", "Test"]
                )

        self.assertEqual(result, 1)
        self.assertIn("Unable to resolve DNS hostname", output.getvalue())
        self.assertIn("Cisco router DNS configuration", output.getvalue())


if __name__ == "__main__":
    unittest.main()
