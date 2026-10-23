"""Checks that the GraphQL stand-in answers like Stash: only the selected fields come back."""

import unittest

from .stash_stub import project, selection_set


class SelectionTests(unittest.TestCase):
    def test_selection_set_handles_arguments_nesting_and_inline_fragments(self):
        query = """
        query Example($id: ID!) {
          findImage(id: $id) {
            id title
            studio { id name }
            visual_files { ... on ImageFile { path } ... on VideoFile { path } }
          }
        }"""
        self.assertEqual(
            selection_set(query),
            {
                "findImage": {
                    "id": None,
                    "title": None,
                    "studio": {"id": None, "name": None},
                    "visual_files": {"path": None},
                }
            },
        )

    def test_project_drops_unselected_fields_and_nulls_missing_ones(self):
        record = {"id": "1", "title": "Example Image", "studio": {"id": "4", "name": "Example Studio"}, "tags": []}
        selection = {"id": None, "studio": {"id": None}, "code": None}
        self.assertEqual(project(record, selection), {"id": "1", "studio": {"id": "4"}, "code": None})

    def test_project_maps_over_lists(self):
        self.assertEqual(project([{"id": "1", "name": "a"}], {"id": None}), [{"id": "1"}])


if __name__ == "__main__":
    unittest.main()
