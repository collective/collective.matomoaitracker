from collective.matomoaitracker.testing import ACCEPTANCE_TESTING
from collective.matomoaitracker.testing import FUNCTIONAL_TESTING
from collective.matomoaitracker.testing import INTEGRATION_TESTING
from pathlib import Path
from pytest_plone import fixtures_factory


pytest_plugins = ["pytest_plone"]

globals().update(
    fixtures_factory((
        (ACCEPTANCE_TESTING, "acceptance"),
        (FUNCTIONAL_TESTING, "functional"),
        (INTEGRATION_TESTING, "integration"),
    ))
)

STACK_TESTS = Path(__file__).parent / "tests" / "stack"


def pytest_addoption(parser):
    parser.addoption(
        "--stack",
        action="store_true",
        help="run tests/stack against the running Docker stack (make stack-test)",
    )


def pytest_ignore_collect(collection_path, config):
    """The stack tests need the Docker stack, only run them with --stack."""
    if collection_path == STACK_TESTS and not config.getoption("--stack"):
        return True
    return None
