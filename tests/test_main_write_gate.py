import argparse
import unittest

import main


class WriteFlagGateTests(unittest.TestCase):
    """Live Sheets writeback requires the explicit --write flag."""

    @staticmethod
    def _args(write=False, dry_run=False, adoptions_file=None):
        return argparse.Namespace(
            write=write, dry_run=dry_run, adoptions_file=adoptions_file
        )

    def test_default_run_is_dry_run(self):
        self.assertTrue(main._resolve_dry_run(self._args()))

    def test_explicit_dry_run_flag_alone_is_dry_run(self):
        self.assertTrue(main._resolve_dry_run(self._args(dry_run=True)))

    def test_live_write_requires_the_write_flag(self):
        self.assertFalse(main._resolve_dry_run(self._args(write=True)))

    def test_adoptions_without_write_stay_dry(self):
        self.assertTrue(
            main._resolve_dry_run(self._args(adoptions_file="data/adoptions.json"))
        )

    def test_write_and_dry_run_are_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            main._resolve_dry_run(self._args(write=True, dry_run=True))