# Changes

[![Build](https://github.com/jbmorley/changes/actions/workflows/test.yaml/badge.svg)](https://github.com/jbmorley/changes/actions/workflows/test.yaml)

Lightweight and (hopefully) unopinionated tool for working with [Conventional Commits](https://www.conventionalcommits.org/) and [Semantic Versioning](https://semver.org).

## Overview

Many of the SemVer tools out there force very specific workflows that I found hard to adopt in my own projects. Changes attempts to provide a collection of tools that fit into your own project lifecycle.

## Installation

```bash
git clone git@github.com:jbmorley/changes.git
cd changes
pipenv install
```

## Usage

```bash
changes --help
```

You can also find out details of specific sub-commands by passing the `--help` flag directly to those commands. For example,

```bash
changes release --help
```

## Development

### Tests

Run tests locally using the `test.sh` script:

```bash
./scripts/test.sh
```

You can run a specific test by specifying the test class on the command line:

```bash
./scripts/test.sh test_cli.CLITestCase.test_version_multiple_changes_yield_single_increment
```
