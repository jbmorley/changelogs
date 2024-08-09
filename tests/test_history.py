#!/usr/bin/env python3

# Copyright (c) 2021 InSeven Limited
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import subprocess
import unittest

import common

from common import EmptyCommit, Repository, Tag

import changes

from changes import Change, History, Message, Type, Version


class HistoryTestCase(unittest.TestCase):

    def test_history_augmentation(self):
        with Repository() as repository:
            repository.perform([
                EmptyCommit("initial commit"),
                Tag("21.0.0"),
            ])
            history = History(path=repository.path)
            self.assertEqual(len(history.releases), 1)
            repository.write_file("history.yaml", """
"1.0.0": []
"2.0.0":
- "feat: New feature"
            """)
            history = History(path=repository.path, history=os.path.join(repository.path, "history.yaml"))
            self.assertEqual(len(history.releases), 3)
            versions = [str(release.version) for release in history.releases]
            self.assertEqual(versions, ["21.0.0", "2.0.0", "1.0.0"])

            repository.write_yaml("history.yaml", {
                "2.0.0": [
                    "feat: New feature",
                ]
            })
            history = History(path=repository.path, history=os.path.join(repository.path, "history.yaml"))
            self.assertEqual(len(history.releases), 2)
            versions = [str(release.version) for release in history.releases]
            self.assertEqual(versions, ["21.0.0", "2.0.0"])
            self.assertEqual(history.releases[1].changes, [Change(Message(type=Type.FEATURE, scope=None, breaking_change=False, description="New feature"))])
            self.assertNotEqual(history.releases[1].changes, [Change(Message(type=Type.FIX, scope=None, breaking_change=False, description="New feature"))])

    def test_invalid_configuraiton_fails(self):
        with Repository() as repository:
            repository.write_yaml("history.yaml", {
                "key": "string"
            })
            with self.assertRaises(Exception):
                changes.load_history(os.path.join(repository.path, "history.yaml"))
            repository.write_yaml("history.yaml", {
                "2.4.5": "string"
            })
            with self.assertRaises(ValueError):
                changes.load_history(os.path.join(repository.path, "history.yaml"))

    def test_scope_filtering(self):
        with Repository() as repository:
            repository.write_yaml("history.yaml", {
                "macOS_1.4.0": [
                    "feat: Foo",
                    "feat: Bar",
                    "feat: Baz",
                ],
                "macOS_1.3.4": [
                    "fix: Minor",
                ],
                "1.0.4": [
                    "fix: Cheese",
                ]
            })

            releases = changes.load_history(os.path.join(repository.path, "history.yaml"), prefix="macOS")
            self.assertEqual(len(releases), 2)
            self.assertEqual(list(sorted(releases.keys())), [Version(1, 3, 4, prefix="macOS"), Version(1, 4, 0, prefix="macOS")])

            releases = changes.load_history(os.path.join(repository.path, "history.yaml"), prefix=None)
            self.assertEqual(len(releases), 1)
            self.assertEqual(list(sorted(releases.keys())), [Version(1, 0, 4)])

            releases = changes.load_history(os.path.join(repository.path, "history.yaml"), prefix="cheese")
            self.assertEqual(len(releases), 0)

    # TODO: Ensure pre-release versions can come from the history.

    # TODO: Test history replacement is prefix sensitive


if __name__ == '__main__':
    unittest.main()
