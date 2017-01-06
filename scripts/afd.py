#!/usr/bin/env python3


import collections
from io import StringIO
from lxml import etree
import pprint
import requests
from urllib.parse import urljoin


INDEX_URI = 'https://en.wikipedia.org/wiki/Wikipedia:Articles_for_deletion'
CURRENT_ID = 'Current_discussions'
OLD_ID = 'Old_discussions'


def child_matching(el, f, start=0):
    """Return the index of the first child matching f."""
    i = start
    while i < len(el):
        if f(el[i]):
            return i
        i += 1
    return None


def has_span(id_value, el):
    """Does the element contain span[@id=id_value]?"""
    for span in el.findall('span'):
        if span.get('id') == id_value:
            return True
    return False


def find_h3(parent, id_value, start=0):
    """Find the index of an h3 that has_span id_value or raise hell."""
    i = child_matching(
        parent,
        lambda e: e.tag == 'h3' and has_span(id_value, e),
        start=start,
    )
    if i is None:
        raise Exception('Unable to find #{}.'.format(id_value))
    return i


def find_ul(parent, start=0):
    """Find the next ul."""
    i = child_matching(parent, lambda e: e.tag == 'ul', start=start)
    if i is None:
        raise Exception('Unable to find list.')
    return i


def find_links(parent, base_uri):
    """Walk all the descendents of a node and return any URLs linked to."""
    for a in parent.findall('.//a'):
        href = a.get('href')
        if href is not None:
            yield urljoin(base_uri, href)


def get_content(uri, parser):
    """Retrieves the document at uri and returns #mw-content-text."""
    r = requests.get(uri)
    tree = etree.parse(StringIO(r.text), parser)
    return tree.getroot().find('.//div[@id="mw-content-text"]')


def iter_h3_ul_links(parent, id_value, base_uri, start=0):
    """Finds h3/span[@id=id_value], then the next ul and returns all the
    links found in the list."""
    cursor = start
    cursor = find_h3(parent, id_value, cursor)
    cursor = find_ul(parent, cursor)
    return (cursor, find_links(parent[cursor], base_uri))


def get_afd_index(base_uri, parser):
    """This retrieves the AfD index page and returns the links to the weekly
    pages."""
    content = get_content(base_uri, parser)
    cursor = 0
    cursor, links = iter_h3_ul_links(content, CURRENT_ID, INDEX_URI, cursor)
    yield from links
    _, links = iter_h3_ul_links(content, OLD_ID, INDEX_URI, cursor)
    yield from links


def main():
    parser = etree.HTMLParser()
    for link in get_afd_index(INDEX_URI, parser):
        pass


if __name__ == '__main__':
    main()
