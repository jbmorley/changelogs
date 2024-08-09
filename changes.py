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

import argparse
import collections
import copy
import enum
import logging
import os
import re
import subprocess
import sys
import tempfile

import jinja2
import yaml

import cli


CHANGES_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIRECTORY = os.path.join(CHANGES_DIRECTORY, "templates")

MULTIPLE_RELEASE_TEMPLATE = "multiple.markdown"
SINGLE_RELEASE_TEMPLATE = "single.markdown"


class Type(enum.Enum):
    CI = "ci"
    DOCUMENTATION = "docs"
    FEATURE = "feat"
    FIX = "fix"
    UNKNOWN = "UNKNOWN"


class Sections(enum.Enum):
    IGNORE = "IGNORE"
    CHANGES = "CHANGES"
    FIXES = "FIXES"


OPERATIONS = {
    Type.CI: None,
    Type.DOCUMENTATION: None,
    Type.FEATURE: lambda commit, version: version.bump_minor(),
    Type.FIX: lambda commit, version: version.bump_patch(),
    Type.UNKNOWN: None,
}


TYPE_TO_SECTION = {
    Type.CI: Sections.IGNORE,
    Type.DOCUMENTATION: Sections.IGNORE,
    Type.FEATURE: Sections.CHANGES,
    Type.FIX: Sections.FIXES,
    Type.UNKNOWN: Sections.IGNORE,
}


SECTION_TITLES = {
    Sections.CHANGES: "Changes",
    Sections.FIXES: "Fixes",
}


class Chdir(object):

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def __enter__(self):
        self.pwd = os.getcwd()
        os.chdir(self.path)
        return self.path

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir(self.pwd)


class PreRelease(object):

    def __init__(self, prefix, version=0):
        self.prefix = prefix
        self.version = version
        self._did_update = False

    def bump(self):
        if self._did_update:
            return
        self._did_update = True
        self.version = self.version + 1

    def __str__(self):
        if self.version:
            return f"{self.prefix}.{self.version}"
        return self.prefix

    def __eq__(self, other):
        if not isinstance(other, PreRelease):
            return False
        if self.prefix != other.prefix:
            return False
        if self.version != other.version:
            return False
        return True

    def __lt__(self, other):
        if self == other:
            return False
        if self.prefix > other.prefix:
            return False
        if self.prefix < other.prefix:
            return True
        if self.version > other.version:
            return False
        if self.version < other.version:
            return True
        return True


class Version(object):

    def __init__(self, major=0, minor=0, patch=0, pre_release=None, prefix=None):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prefix = prefix
        self.pre_release = pre_release
        self._did_update_major = False
        self._did_update_minor = False
        self._did_update_patch = False

    def bump_major(self):
        assert self.pre_release is None, "Version bumps are not supported for pre-release versions."
        if self._did_update_major:
            return
        self.major = self.major + 1
        self.minor = 0
        self.patch = 0
        self._did_update_major = True

    def bump_minor(self):
        assert self.pre_release is None, "Version bumps are not supported for pre-release versions."
        if self._did_update_minor or self._did_update_major:
            return
        self.minor = self.minor + 1
        self.patch = 0
        self._did_update_minor = True

    def bump_patch(self):
        assert self.pre_release is None, "Version bumps are not supported for pre-release versions."
        if self._did_update_patch or self._did_update_minor or self._did_update_major:
            return
        self.patch = self.patch + 1
        self._did_update_patch = True

    @property
    def is_initial_development(self):
        if self.major == 0:
            return True
        return False

    @property
    def is_pre_release(self):
        return self.pre_release is not None

    def __str__(self):
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.is_pre_release:
            version = version + f"-{str(self.pre_release)}"
        return version

    def qualifiedString(self):
        version = str(self)
        if self.prefix:
            version = f"{self.prefix}_" + version
        return version

    def __eq__(self, other):
        if not isinstance(other, Version):
            return False
        if self.major != other.major:
            return False
        if self.minor != other.minor:
            return False
        if self.patch != other.patch:
            return False
        if self.pre_release != other.pre_release:
            return False
        if self.prefix != other.prefix:
            return False
        return True

    def __lt__(self, other):
        if self == other:
            return False
        if ("" if self.prefix is None else self.prefix) > ("" if other.prefix is None else other.prefix):
            return False
        if ("" if self.prefix is None else self.prefix) < ("" if other.prefix is None else other.prefix):
            return True
        if self.major > other.major:
            return False
        if self.major < other.major:
            return True
        if self.minor > other.minor:
            return False
        if self.minor < other.minor:
            return True
        if self.patch > other.patch:
            return False
        if self.patch < other.patch:
            return True
        if self.pre_release is None and other.pre_release is not None:
            return False
        if self.pre_release is not None and other.pre_release is None:
            return True
        if self.pre_release is not None and other.pre_release is not None:
            return self.pre_release < other.pre_release
        return True

    def __hash__(self):
        return str(self).__hash__()

    def __repr__(self):
        return "Version(major=%r, minor=%r, patch=%r, pre_release=%r, prefix=%r)" % (self.major,
                                                                                     self.minor,
                                                                                     self.patch,
                                                                                     self.pre_release,
                                                                                     self.prefix)

    @classmethod
    def from_string(self, string, strip_scope=None):
        sv_parser = re.compile(r"^((.+?)_)?(\d+).(\d+).(\d+)(-([A-Za-z]+)(\.(\d+))?)?$")
        match = sv_parser.match(string)
        if match:
            prefix = match.group(2)
            pre_release_prefix = match.group(7)
            pre_release = None
            if pre_release_prefix is not None:
                pre_release_version = int(match.group(9)) if match.group(9) is not None else 0
                pre_release = PreRelease(pre_release_prefix, pre_release_version)  # TODO: This might be cleaner as a 'sub-version' or similar?
            return Version(major=int(match.group(3)),
                           minor=int(match.group(4)),
                           patch=int(match.group(5)),
                           pre_release=pre_release,
                           prefix=prefix)
        raise ValueError("'%s' is not a valid version." % string)


class Change(object):

    def __init__(self, message):
        self.message = message

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return self.message == other.message

    def __str__(self):
        return str(self.message)


class Commit(Change):

    def __init__(self, sha, message, tags, versions):
        super().__init__(message)
        self.sha = sha
        self.tags = tags
        self.versions = versions


class Message(object):

    def __init__(self, type, scope, breaking_change, description):
        self.type = type
        self.scope = scope
        self.breaking_change = breaking_change
        self.description = description

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        if self.type != other.type:
            return False
        if self.scope != other.scope:
            return False
        if self.breaking_change != other.breaking_change:
            return False
        if self.description != other.description:
            return False
        return True

    def __str__(self):
        return self.description


class Group(object):

    def __init__(self, identifier, items):
        self.identifier = identifier
        self.items = items

    def __repr__(self):
        return "Group(identiifer=%r, items=%r)" % (self.identifier, self.items)


# TODO: Consider reusing this?
def group(items, identifier):
    results = [Group(None, [])]
    for item in items:
        item_identifier = identifier(item)
        if item_identifier is not None and results[-1].identifier != item_identifier:
            results.append(Group(item_identifier, []))
        results[-1].items.append(item)
    if not results[0].items:
        results.pop(0)
    return results


class Release(object):

    def __init__(self, version, changes, is_released=False):
        self.version = version
        self.changes = changes
        self.is_released = is_released

    def calculate_version(self, previous_released_version, pre_release_prefix=None):
        """Recomputes the current version based on the previous version by applying the changes in order."""

        # Copy the previous version so we can update it, accounting for the changes in this release.
        if previous_released_version.is_pre_release:
            raise AssertionError("Incorrectly created a relese with a pre-release verison (%s)." % (previous_released_version, ))

        self.version = copy.deepcopy(previous_released_version)

        # Iterate over all the changes that are in this release and determine the version number.
        for commit in reversed(self.changes):
            if commit.message.type in OPERATIONS and OPERATIONS[commit.message.type] is not None:
                if commit.message.breaking_change:
                    self.version.bump_major()
                else:
                    OPERATIONS[commit.message.type](commit, self.version)
            else:
                logging.warning("Ignoring commit: '%s'", commit.message.description)

        # If we're not being asked to generate a pre-release version we're finished.
        if pre_release_prefix is None:
            return

        def relevant_pre_release_version(commit):
            pre_release_versions = sorted([version for version in commit.versions
                                           if (version.is_pre_release and
                                               version.pre_release.prefix == pre_release_prefix and
                                               self.version.major == version.major and
                                               self.version.minor == version.minor and
                                               self.version.patch == version.patch)])
            if pre_release_versions:
                return pre_release_versions[-1]
            return None

        # Group the commits by version, filtered to match just our current version and requested pre-release prefix.
        commits_by_pre_release = group(reversed(self.changes), relevant_pre_release_version)
        if commits_by_pre_release and commits_by_pre_release[-1].identifier is not None:
            pre_release = copy.deepcopy(commits_by_pre_release[-1].identifier.pre_release)
            pre_release.bump()
            self.version.pre_release = pre_release
        else:
            self.version.pre_release = PreRelease(prefix=pre_release_prefix)

    @property
    def is_empty(self):
        for change in self.changes:
            if OPERATIONS[change.message.type] is not None:
                return False
        return True

    @property
    def is_pre_release(self):
        return self.version.is_pre_release

    @property
    def is_initial_development(self):
        return self.version.is_initial_development

    def merge(self, release):
        self.changes.extend(release.changes)

    @property
    def sections(self):
        return group_changes(self.changes)


class Section(object):

    def __init__(self, type, changes):
        self.type = type
        self.changes = changes

    @property
    def title(self):
        return SECTION_TITLES[self.type]


class History(object):

    def __init__(self,
                 path,
                 scope=None,
                 history=None,
                 skip_unreleased=False,
                 pre_release=False,
                 pre_release_prefix="rc"):
        self.path = os.path.abspath(path)
        self.scope = scope
        self.skip_unreleased = skip_unreleased
        self.history = os.path.abspath(history) if history is not None else None
        self.pre_release = pre_release
        self.pre_release_prefix = pre_release_prefix
        self._load()

    def _load(self):
        with Chdir(self.path):

            if is_shallow():
                logging.error("Unable to determine change history for shallow clones.")
                exit(1)

            # Get all the changes on the current branch.
            all_changes = get_commits(scope=self.scope)

            # Group the changes by release.
            # We create an empty head release to absorb all the changes that don't yet have versions.
            releases = []
            releases.append(Release(None, []))

            # Releases currently being processed by the loop.
            current_releases = [releases[-1]]

            # Iterate over the changes, most recent first.
            for change in all_changes:

                # Iterate over all the relevant version tags (highest version first) on this change and update the
                # current set of releases accordingly.
                change_versions = [version for version in reversed(sorted(change.versions))
                                   if not version.is_pre_release or version.pre_release.prefix == self.pre_release_prefix]
                for change_version in change_versions:

                    # This method is pretty magical as it's the way by which we determine how the changes we see affect
                    # the current set of releases we're dropping changes into as we go through the changes in reverse
                    # chronological order.
                    # In essence, pre-release versions should never affect the active set as pre-release versions are
                    # intentionally overlapping (they collect all changes since the last release version), while
                    # release versions will always displace releases that came after them (including pre-releases).
                    # The only place where this differs is that pre-release versions are allowed to replace _empty_
                    # unreleased versions. This is, in many ways a side effect of a poorly designed loop; we probably
                    # shouldn't insert an empty release until we need one, then we wouldn't need this magic.
                    def version_replaces_release(version, release):
                        if version.is_pre_release:
                            return release.version is None and release.is_empty and self.pre_release
                        return release.version is None or release.version > version

                    # Update the active set of releases.
                    current_releases = [release for release in current_releases
                                        if not version_replaces_release(change_version, release)]

                    # Create a new release for the current change.
                    release = Release(change_version, [], is_released=True)
                    releases.append(release)
                    current_releases.append(release)

                # Append the change to the latest release (which we might have just created).
                for release in current_releases:
                    release.changes.append(change)

            # Fix-up the version number for any un-released current release.
            # `calculate_version` does all the work to determine the version for the release by applying the releases'
            # changes to the previous version.
            if releases[0].version is None:
                # Pass in the previous _released_ version.
                released_versions = [release.version for release in releases[1:] if not release.is_pre_release]
                previous_released_version = released_versions[0] if len(released_versions) > 0 else Version(0, 0, 0)
                releases[0].calculate_version(previous_released_version=previous_released_version,
                                              pre_release_prefix=self.pre_release_prefix if self.pre_release else None)

            # Remove the empty head release if there's already an active release.
            if len(releases) > 1 and releases[0].is_empty:
                releases.pop(0)

            releases_by_version = {release.version: release for release in releases}

            if self.history is not None:
                for version, release in load_history(path=self.history, prefix=self.scope).items():
                    try:
                        releases_by_version[version].merge(release)
                    except KeyError:
                        releases_by_version[version] = release

            releases = list(sorted(releases_by_version.values(),
                                   key=lambda release: release.version, reverse=True))

            # Filter the releases to match our requested state.

            # Filter unreleased versions
            releases = [release for release in releases
                        if release.is_released or not self.skip_unreleased]

            # Filter pre-releases
            releases = [release for release in releases
                        if not release.is_pre_release or self.pre_release]

            self.releases = releases


def load_history(path, prefix=None):
    history = {}
    with open(path) as fh:
        contents = yaml.load(fh, Loader=yaml.SafeLoader)
    # Check the format.
    if not isinstance(contents, dict):
        raise ValueError("Invalid configuration")
    for version_string, changes in contents.items():
        version = Version.from_string(version_string)
        if version.prefix != prefix:
            logging.warning("Ignoring version '%s'...", version_string)
            continue
        if not isinstance(version_string, str) or not isinstance(changes, list):
            raise ValueError("Invalid configuration")
        messages = [parse_message(change) for change in changes]
        commits = [Change(message=message) for message in messages]
        commits.reverse()
        release = Release(version, commits, is_released=True)
        history[version] = release
    return history


def run(command, dry_run=False):
    if dry_run:
        logging.info(command)
        return []
    result = subprocess.run(command, capture_output=True)
    result.check_returncode()
    lines = result.stdout.decode("utf-8").strip().split("\n")
    return lines


def is_shallow():
    return run(["git", "rev-parse", "--is-shallow-repository"])[0] == "true"


def get_tags():
    tags = collections.defaultdict(list)
    for tag in [tag for tag in run(["git", "tag"]) if tag]:
        sha = run(["git", "rev-list", "-n", "1", "tags/%s" % (tag, )])[0]
        tags[sha].append(tag)
    return tags


class UnknownScope(ValueError):
    pass


def versions_from_tags(tags, prefix):
    versions = []
    for tag in tags:
        try:
            version = Version.from_string(tag)
            if version.prefix == prefix:
                versions.append(version)
        except ValueError:
            pass
    return versions


def get_commits(scope=None):

    # Guard against empty repositories.
    count = int(run(["git", "rev-list", "--all", "--count"])[0])
    if count < 1:
        return []

    # Load the tags and versions.
    tags = get_tags()
    versions = collections.defaultdict(list)
    for sha, sha_tags in tags.items():
        versions[sha] = versions_from_tags(sha_tags, prefix=scope)

    results = []
    command = ["git", "log", "--pretty=format:%H:%s"]
    try:
        commits = run(command)
    except subprocess.CalledProcessError as e:
        logging.error(e.stderr.decode("utf-8"))
        exit(1)
    for c in commits:
        sha, message = c.split(":", 1)
        commit = Commit(sha, parse_message(message), tags[sha], versions[sha])
        results.append(commit)
    return results


def parse_message(message):
    cc_parser = re.compile(r"^(.+?)(\((.+?)\))?(\!)?:(.+)$")
    match = cc_parser.match(message)
    if match is not None:
        (cc_type, cc_scope, cc_break, cc_description) = (match.group(1), match.group(3), match.group(4), match.group(5))
        try:
            return Message(type=Type(cc_type),
                           scope=cc_scope,
                           breaking_change=(cc_break == "!"),
                           description=cc_description.strip())
        except ValueError:
            pass
    return Message(type=Type.UNKNOWN,
                   scope=None,
                   breaking_change=False,
                   description=message.strip())


def group_changes(changes):
    sections = {}
    for commit in changes:
        section_type = TYPE_TO_SECTION[commit.message.type]
        if section_type not in sections:
            sections[section_type] = Section(type=section_type, changes=[])
        section = sections[section_type]
        section.changes.append(commit.message)
    results = []
    if Sections.CHANGES in sections:
        results.append(sections[Sections.CHANGES])
    if Sections.FIXES in sections:
        results.append(sections[Sections.FIXES])
    return results


def format_notes(releases, template):
    loader = jinja2.ChoiceLoader([
        AbsolutePathLoader(),
        jinja2.FileSystemLoader(TEMPLATES_DIRECTORY),
    ])
    environment = jinja2.Environment(loader=loader)
    return environment.get_template(template).render(releases=releases, Sections=Sections).rstrip() + "\n"


def resolve_scope(options):
    if options.scope is not None:
        return options.scope
    try:
        return options.legacy_scope
    except AttributeError:
        return None


@cli.command("version", help="output the current version as determined by taking the the most recent version tag and applying any subsequent changes; if there have been no changes since the most recent version tag, this will output the version of the most recent tag", arguments=[
    cli.Argument("--scope", help="scope to be used in tags and commit messages"),
    cli.Argument("--released", action="store_true", default=False, help="scope to be used in tags and commit messages"),
    cli.Argument("--pre-release", action="store_true", default=False, help="generate a pre-release version"),
    cli.Argument("--pre-release-prefix", type=str, default="rc", help="prefix to be used when generating a pre-release version (defaults to 'rc')"),
])
def command_version(options):
    history = History(path=os.getcwd(),
                      scope=resolve_scope(options),
                      skip_unreleased=options.released,
                      pre_release=options.pre_release,
                      pre_release_prefix=options.pre_release_prefix)
    print(history.releases[0].version)


@cli.command("release", help="tag the commit as a new release", formatter_class=argparse.RawDescriptionHelpFormatter, arguments=[
    cli.Argument("--scope", help="scope to be used in tags and commit messages"),
    cli.Argument("--skip-if-empty", action="store_true", default=False, help="exit cleanly if there are no changes to release"),
    cli.Argument("--command", help="additional command to run during the release; if the command fails, the release will be rolled back (cannot be used alongside --exec)"),
    cli.Argument("--exec", help="executable to run to during the release; if the executable fails, the release will be rolled back (cannot be used alongside --command)"),
    cli.Argument("--push", action="store_true", default=False, help="push the newly created tag"),
    cli.Argument("--dry-run", action="store_true", default=False, help="perform a dry run, only logging the operations that would be performed"),
    cli.Argument("--template", help="custom Jinja2 template"),
    cli.Argument("--pre-release", action="store_true", default=False, help="generate a pre-release version"),
    cli.Argument("--pre-release-prefix", type=str, default="rc", help="prefix to be used when generating a pre-release version (defaults to 'rc')"),
    cli.Argument("arguments", nargs="*", help="arguments to pass to the release command"),
], epilog="""
When calling a script specified by `--command` or `--exec`, Changes defines a number of environment variables:

  CHANGES_TITLE                a proposed title for the release
  CHANGES_QUALIFIED_TITLE      a proposed title including pre-release version details (if applicable)
  CHANGES_VERSION              version number
  CHANGES_QUALIFIED_VERSION    full version number including pre-release version details (if applicable)
  CHANGES_INITIAL_DEVELOPMENT  true if the major version number is less than 0; false otherwise
  CHANGES_PRE_RELEASE          true if the release is a pre-release; false otherwise
  CHANGES_TAG                  the Git tag used for the release
  CHANGES_NOTES                the release notes
  CHANGES_NOTES_FILE           path to a file containing the release notes
""")
def command_release(options):

    if options.command is not None and options.exec is not None:
        logging.error("--command and --exec cannot be used together.")
        exit(1)

    scope = resolve_scope(options)
    history = History(path=os.getcwd(),
                      scope=scope,
                      pre_release=options.pre_release,
                      pre_release_prefix=options.pre_release_prefix)
    releases = history.releases
    if releases[0].is_released or releases[0].is_empty:
        # There aren't any unreleased versions.
        if options.skip_if_empty:
            exit()
        logging.error("No versions to release.")
        exit(1)
    version = releases[0].version
    logging.info("Releasing %s...", version)
    tag = str(version)
    if scope is not None:
        tag = f"{scope}_{tag}"
    logging.info("Creating tag '%s'...", tag)
    run(["git", "tag", tag], dry_run=options.dry_run)

    title = f"{version.major}.{version.minor}.{version.patch}"
    if scope is not None:
        title = f"{scope} {title}"
    qualified_title = title
    if version.is_pre_release:
        qualified_title = f"{qualified_title} {version.pre_release}"

    if options.push:
        logging.info("Pushing tag '%s'...", tag)
        run(["git", "push", "origin", tag], dry_run=options.dry_run)

    if options.command is not None or options.exec is not None:
        logging.info("Running command...")
        success = True

        if options.template is not None:
            template = os.path.abspath(options.template)
        else:
            template = SINGLE_RELEASE_TEMPLATE
        notes = format_notes(releases=[releases[0]], template=template)

        with tempfile.NamedTemporaryFile() as notes_file, tempfile.TemporaryDirectory() as temporary_directory:

            # Create a temporary directory containing the notes.
            with open(notes_file.name, "w") as fh:
                fh.write(notes)

            # Create a temporary executable script to make it easy to forward arguments to the command.
            if options.command is not None:
                command = os.path.join(temporary_directory, "script.sh")
                with open(command, "w") as fh:
                    fh.write("#!/bin/sh\n")
                    fh.write(options.command)
                os.chmod(command, 0o744)
            elif options.exec is not None:
                command = os.path.abspath(options.exec)

            # Set up the environment.
            env = copy.deepcopy(os.environ)
            env['CHANGES_TITLE'] = title
            env['CHANGES_QUALIFIED_TITLE'] = qualified_title
            env['CHANGES_VERSION'] = f"{version.major}.{version.minor}.{version.patch}"
            env['CHANGES_QUALIFIED_VERSION'] = str(version)
            env['CHANGES_PRE_RELEASE_VERSION'] = str(version.pre_release) if version.pre_release is not None else ""
            env['CHANGES_INITIAL_DEVELOPMENT'] = "true" if version.is_initial_development else "false"
            env['CHANGES_PRE_RELEASE'] = "true" if version.is_pre_release else "false"
            env['CHANGES_TAG'] = tag
            env['CHANGES_NOTES'] = notes
            env['CHANGES_NOTES_FILE'] = notes_file.name

            # Run the command.
            command_args = [command] + options.arguments
            if options.dry_run:
                logging.info("Running command '%s'...", command_args)
            else:
                logging.debug("Running command '%s' in directory '%s' with files '%s'...", command_args, os.getcwd(), os.listdir())
                result = subprocess.run(command_args, capture_output=True, env=env)
                try:
                    result.check_returncode()
                    logging.info(result.stdout.decode("utf-8").strip())
                except subprocess.CalledProcessError as e:
                    logging.info(result.stdout.decode("utf-8").strip())
                    logging.error("Release command failed with error '%s'; reverting release.", e.stderr.decode("utf-8").strip())
                    run(["git", "tag", "-d", tag])
                    if options.push:
                        run(["git", "push", "origin", f":{tag}"])
                    success = False

        if not success:
            exit(1)

    logging.info("Done.")


class AbsolutePathLoader(jinja2.BaseLoader):

    def get_source(self, environment, template):
        path = os.path.abspath(template)
        if not os.path.exists(path):
            raise jinja2.TemplateNotFound(path)
        mtime = os.path.getmtime(path)
        with open(path) as f:
            source = f.read()
        return source, path, lambda: mtime == os.path.getmtime(path)


@cli.command("notes", help="output the release notes", arguments=[
    cli.Argument("--scope", help="filter the release notes to the given scope"),
    cli.Argument("--skip-unreleased", action="store_true", help="skip unreleased versions"),
    cli.Argument("--history", help="file containing changes for versions not adhereing to Conventional Commits"),
    cli.Argument("--released", action="store_true", default=False, help="show only released versions; display the most recent released version, or all versions if the '--all' flag is specified"),
    cli.Argument("--pre-release", action="store_true", default=False, help="include pre-release versions"),
    cli.Argument("--pre-release-prefix", type=str, default="rc", help="prefix to be used when generating a pre-release version (defaults to 'rc')"),
    cli.Argument("--all", action="store_true", default=False, help="output release notes for all versions"),
    cli.Argument("--template", help="custom Jinja2 template")
])
def command_notes(options):
    history = History(path=os.getcwd(),
                      history=options.history,
                      scope=resolve_scope(options),
                      skip_unreleased=options.released,
                      pre_release=options.pre_release,
                      pre_release_prefix=options.pre_release_prefix)

    if options.template is not None:
        template = os.path.abspath(options.template)
    else:
        template = MULTIPLE_RELEASE_TEMPLATE if options.all else SINGLE_RELEASE_TEMPLATE

    if options.all:
        print(format_notes(releases=history.releases, template=template), end="")
    else:
        print(format_notes(releases=[history.releases[0]], template=template), end="")


@cli.command("scopes", help="show all the unique scopes used within the repository")
def command_scopes(options) -> None:
    scopes = set([commit.message.scope for commit in get_commits() if commit.message.scope is not None])
    for scope in sorted(scopes):
      print(scope)


DESCRIPTION = """

Lightweight and (hopefully) unopinionated tool for managing Semantic Versioning using Conventional Commits.

Changes currently a number of commands that can be assembled in whatever way fits your workflow.
"""

EPILOG = """
You can find out more about Conventional Commits and Semantic Versioning at the following links:

- Conventional Commits: https://www.conventionalcommits.org
- Semantic Versioning: https://semver.org
"""

def main():
    verbose = '--verbose' in sys.argv[1:] or '-v' in sys.argv[1:]
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="[%(levelname)s] %(message)s")
    parser = cli.CommandParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--verbose', '-v', action='store_true', default=False, help="show verbose output")
    if "--scope" in sys.argv:
        parser.add_argument("--scope", dest="legacy_scope", help="scope to be used in tags and commit messages")
    parser.run()


if __name__ == "__main__":
    main()
