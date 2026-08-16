"""Pagination shared across the API."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default paging, with an opt-in larger page for pickers.

    Selection controls need the whole candidate list in one request: a dropdown
    that renders page 1 and ignores `next` silently truncates its options, and
    the user cannot tell the difference between "not offered" and "not there".
    `page_size_query_param` lets those callers ask for everything, while
    `max_page_size` stops it becoming an accidental full-table export.
    """

    page_size_query_param = "page_size"
    max_page_size = 500
