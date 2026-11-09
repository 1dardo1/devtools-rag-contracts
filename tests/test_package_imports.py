"""The first tests in the repository, and they are not a formality.

Both services will install this package as a Git dependency, by its
distribution name, and import it by its import root. These tests hold both
halves of that: the distribution is installed under the name a consumer asks
for, and the package it provides imports and says what it is for. ADR 0006.
"""

import importlib
import importlib.metadata


def test_the_distribution_is_installed_under_its_published_name() -> None:
    assert importlib.metadata.version("devtools-rag-contracts")


def test_the_package_imports_and_documents_itself() -> None:
    module = importlib.import_module("rag_contracts")

    assert module.__doc__, "rag_contracts should say what the package is for"
