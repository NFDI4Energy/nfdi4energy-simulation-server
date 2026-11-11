"""The SimaaS pandapower image must not execute code from uploaded network files.

network_loader.py is a verbatim copy of the upstream DaceDSX module (PR 0);
these tests only check that this wrapper copy routes through it.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import pandapower as pp
import pandapower.networks as pn

WRAPPER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WRAPPER))
from network_loader import ALLOW_PICKLE_ENV, UnsafeNetworkError
from pandapowerApi import pandapowerAPI


class WrapperLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        os.environ.pop(ALLOW_PICKLE_ENV, None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pickle_is_refused(self):
        path = self.dir / "net.p"
        pp.to_pickle(pn.case9(), str(path))
        with self.assertRaises(UnsafeNetworkError):
            pandapowerAPI(str(path), n_steps=1).init()

    def test_json_with_foreign_module_is_refused(self):
        path = self.dir / "net.json"
        path.write_text(json.dumps({"_module": "os", "_class": "system", "_object": "id"}))
        with self.assertRaises(UnsafeNetworkError):
            pandapowerAPI(str(path), n_steps=1).init()

    def test_pandapower_json_loads(self):
        path = self.dir / "net.json"
        pp.to_json(pn.case9(), str(path))
        api = pandapowerAPI(str(path), n_steps=1)
        api.init()
        self.assertEqual(len(api.network.bus), 9)

    def test_example_dict_network_loads(self):
        api = pandapowerAPI(str(WRAPPER / "examples" / "network.json"), n_steps=1)
        api.init()
        self.assertEqual(api.network.name, "example_network")


if __name__ == "__main__":
    unittest.main()
