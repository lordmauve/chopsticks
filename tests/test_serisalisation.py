"""Tests for Chopstick's various forms of serialisation."""
import sys
import xml.etree
from unittest import TestCase
from chopsticks.serialise_main import serialise_func, deserialise_func


# A constant, sent by value
CONST = 5

# This constant should not be serialised, because it is unused
UNUSED_CONST = 7


# Create an alias for the xml module
xml_processing = xml


def bar():
    xml_processing  # Just reference this import to ensure it is serialised
    return list(range(CONST))


def foo():
    """Test function to be serialised, calls bar()."""
    return bar()[-2:]


# Trigger the serialisation behaviour
foo.__module__ = bar.__module__ = '__main__'



class SerialisationTest(TestCase):
    """We can serialise a function as source."""

    def setUp(self):
        (self.source, self.name, self.imports,
         self.imported_names, self.variables) = serialise_func(foo)

    def test_serialise_source(self):
        """The source code for foo() and bar() is included."""
        self.assertIn('bar()[-2:]', self.source)
        self.assertIn('list(range(CONST))', self.source)

    def test_name(self):
        """The name of the function we serialised is 'foo'."""
        self.assertEqual(self.name, 'foo')

    def test_globals(self):
        """We find the global variables needed."""
        self.assertEqual(self.variables, {
            'CONST': 5
        })

    def test_imported_names(self):
        """We find the modules that are imported into the namespace."""
        self.assertEqual(self.imported_names, {'xml_processing': 'xml'})

    def test_imports(self):
        """Any name that has been imported appears in imports."""
        for mod in ['xml', 'xml.etree']:
            self.assertIn(mod, self.imports)

    def test_deserialise(self):
        """The deserialised function works."""
        f = deserialise_func(
            self.source,
            self.name,
            self.imports,
            self.imported_names,
            self.variables
        )
        self.assertEqual(f(), [3, 4])

