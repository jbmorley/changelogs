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

import changes

from changes import PreRelease, Version


class VersionTestCase(unittest.TestCase):

    def test_str(self):
        self.assertEqual(str(Version()), "0.0.0")
        self.assertEqual(str(Version(0, 1, 1)), "0.1.1")
        self.assertEqual(str(Version(2, 10, 5)), "2.10.5")
        self.assertEqual(str(Version(1, 0, 0, PreRelease("rc"))), "1.0.0-rc")
        self.assertEqual(str(Version(1, 0, 0, PreRelease("rc", 0))), "1.0.0-rc")
        self.assertEqual(str(Version(1, 0, 0, PreRelease("rc", 3))), "1.0.0-rc.3")
        self.assertEqual(str(Version(2, 3, 4, PreRelease("candidate", 100), prefix="macOS")), "2.3.4-candidate.100")
        self.assertEqual(Version(2, 3, 4, PreRelease("candidate", 100), prefix="macOS").qualifiedString(), "macOS_2.3.4-candidate.100")
        self.assertEqual(str(Version(0, 1, 1, prefix="iOS")), "0.1.1")
        self.assertEqual(Version(0, 1, 1, prefix="iOS").qualifiedString(), "iOS_0.1.1")

    def test_comparators(self):

        # Equals.
        self.assertEqual(Version(), Version())
        self.assertEqual(Version(1, 10, 5), Version(1, 10, 5))
        self.assertNotEqual(Version(1, 10, 5), Version(2, 10, 5))
        self.assertNotEqual(Version(1, 10, 5), Version(1, 11, 5))
        self.assertNotEqual(Version(1, 10, 5), Version(1, 10, 10))
        self.assertEqual(Version(pre_release=PreRelease("rc", 0)), Version(pre_release=PreRelease("rc", 0)))
        self.assertEqual(Version(20, 2, 10, PreRelease("rc", 0)), Version(20, 2, 10, PreRelease("rc", 0)))
        self.assertNotEqual(Version(20, 2, 10, PreRelease("rc", 0)), Version(20, 2, 10, PreRelease("alpha", 0)))
        self.assertNotEqual(Version(20, 2, 10, PreRelease("rc", 0)), Version(20, 2, 10, PreRelease("rc", 10)))
        self.assertNotEqual(Version(), Version(pre_release=PreRelease("rc", 0)))
        self.assertEqual(Version(20, 2, 10, prefix="fromage"), Version(20, 2, 10, prefix="fromage"))
        self.assertNotEqual(Version(20, 2, 10, prefix="fromage"), Version(20, 2, 10, prefix="cheese"))

        # Less-than.
        self.assertFalse(Version() < Version())
        self.assertTrue(Version() < Version(0, 1, 4))
        self.assertTrue(Version(1, 0, 0) < Version(2, 0, 0))
        self.assertTrue(Version(1, 0, 0) < Version(1, 1, 0))
        self.assertTrue(Version(1, 0, 0) < Version(1, 0, 1))
        self.assertFalse(Version(1, 0, 0) < Version(1, 0, 0))
        self.assertFalse(Version(2, 0, 0) < Version(1, 0, 0))
        self.assertFalse(Version(1, 2, 0) < Version(1, 1, 0))
        self.assertFalse(Version(1, 1, 2) < Version(1, 1, 1))
        self.assertTrue(Version(0, 1, 0) < Version(1, 0, 0))
        self.assertTrue(Version.from_string("1.0.0-alpha") < Version.from_string("1.0.0"))
        self.assertFalse(Version.from_string("1.0.0") < Version.from_string("1.0.0-alpha"))
        self.assertTrue(Version.from_string("1.0.0-alpha") < Version.from_string("1.0.0-beta"))
        self.assertFalse(Version.from_string("1.0.0-beta") < Version.from_string("1.0.0-alpha"))
        self.assertTrue(Version.from_string("1.0.0-rc") < Version.from_string("1.0.0-rc.3"))
        self.assertFalse(Version.from_string("1.0.0-rc.3") < Version.from_string("1.0.0-rc"))
        self.assertTrue(Version.from_string("1.0.0-rc.2") < Version.from_string("1.0.0-rc.3"))
        self.assertFalse(Version.from_string("1.0.0-rc.3") < Version.from_string("1.0.0-rc.2"))
        self.assertTrue(Version.from_string("0.2.2") < Version.from_string("0.2.3-rc"))
        self.assertTrue(Version.from_string("alpha_1.0.0") < Version.from_string("beta_1.0.0"))
        self.assertTrue(Version.from_string("beta_1.0.0") < Version.from_string("gamma_1.0.0"))
        self.assertFalse(Version.from_string("beta_1.0.0") > Version.from_string("gamma_1.0.0"))

    def test_from_string(self):
        self.assertEqual(Version.from_string("1.5.7"), Version(1, 5, 7))
        self.assertEqual(Version.from_string("0.23.0"), Version(0, 23, 0))
        self.assertEqual(Version.from_string("0.0.0"), Version())
        self.assertEqual(Version.from_string("macOS_1.4.6"), Version(1, 4, 6, prefix="macOS"))
        self.assertEqual(Version.from_string("1.5.9-rc"), Version(1, 5, 9, PreRelease("rc", 0)))
        self.assertEqual(Version.from_string("1.5.9-rc.0"), Version(1, 5, 9, PreRelease("rc", 0)))
        self.assertEqual(Version.from_string("1.5.9-alpha.34"), Version(1, 5, 9, PreRelease("alpha", 34)))

    def test_sort(self):
        input = [
            "1.2.3",
            "0.0.0",
            "12.0.6",
            "0.1.0",
            "0.0.0",
        ]
        output = [
            "0.0.0",
            "0.0.0",
            "0.1.0",
            "1.2.3",
            "12.0.6",
        ]
        input_versions = [Version.from_string(string) for string in input]
        self.assertNotEqual([version.qualifiedString() for version in input_versions], output)
        self.assertEqual([version.qualifiedString() for version in sorted(input_versions)], output)

        input = [
            "a_1.2.3",
            "b_0.0.0",
            "a_12.0.6",
            "b_0.1.0",
            "a_0.0.0",
        ]
        output = [
            "a_0.0.0",
            "a_1.2.3",
            "a_12.0.6",
            "b_0.0.0",
            "b_0.1.0",
        ]
        input_versions = [Version.from_string(string) for string in input]
        self.assertNotEqual([version.qualifiedString() for version in input_versions], output)
        self.assertEqual([version.qualifiedString() for version in sorted(input_versions)], output)

    def test_initial_development(self):
        self.assertTrue(Version().is_initial_development)
        self.assertTrue(Version(0, 1, 4).is_initial_development)
        self.assertTrue(Version(0, 0, 1).is_initial_development)
        self.assertTrue(Version(0, 20, 0).is_initial_development)
        self.assertFalse(Version(1, 0, 0).is_initial_development)
        self.assertFalse(Version(200, 1, 0).is_initial_development)
        self.assertFalse(Version(2, 0, 10).is_initial_development)

    def test_is_pre_release(self):
        self.assertFalse(Version().is_pre_release)
        self.assertFalse(Version(0, 1, 4).is_pre_release)
        self.assertFalse(Version(0, 0, 1).is_pre_release)
        self.assertFalse(Version(0, 20, 0).is_pre_release)
        self.assertFalse(Version(1, 0, 0).is_pre_release)
        self.assertFalse(Version(200, 1, 0).is_pre_release)
        self.assertFalse(Version(2, 0, 10).is_pre_release)
        self.assertTrue(Version(1, 0, 0, PreRelease("rc")).is_pre_release)
        self.assertTrue(Version(1, 0, 0, PreRelease("rc", 0)).is_pre_release)
        self.assertTrue(Version(1, 0, 0, PreRelease("rc", 3)).is_pre_release)

    def test_increment(self):
        version = Version(1, 0, 0)
        version.bump_major()
        self.assertEqual(str(version), "2.0.0")
        version.bump_major()
        self.assertEqual(str(version), "2.0.0")

        version = Version(1, 0, 0)
        version.bump_minor()
        self.assertEqual(str(version), "1.1.0")
        version.bump_minor()
        self.assertEqual(str(version), "1.1.0")

        version = Version(1, 0, 0)
        version.bump_patch()
        self.assertEqual(str(version), "1.0.1")
        version.bump_patch()
        self.assertEqual(str(version), "1.0.1")

        version = Version(1, 0, 0)
        version.bump_minor()
        self.assertEqual(str(version), "1.1.0")
        version.bump_major()
        self.assertEqual(str(version), "2.0.0")
        version.bump_minor()
        self.assertEqual(str(version), "2.0.0")

        version = Version(1, 0, 0)
        version.bump_patch()
        self.assertEqual(str(version), "1.0.1")
        version.bump_major()
        self.assertEqual(str(version), "2.0.0")
        version.bump_patch()
        self.assertEqual(str(version), "2.0.0")

        with self.assertRaises(AssertionError):
            Version(2, 1, 0, PreRelease("alpha", 0)).bump_major()
        with self.assertRaises(AssertionError):
            Version(2, 1, 0, PreRelease("alpha", 0)).bump_minor()
        with self.assertRaises(AssertionError):
            Version(2, 1, 0, PreRelease("alpha", 0)).bump_patch()


if __name__ == '__main__':
    unittest.main()
