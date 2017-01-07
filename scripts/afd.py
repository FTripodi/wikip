#!/usr/bin/env python3


import collections
from lxml import etree
import re
import requests
from urllib.parse import urljoin


INDEX_URI = 'https://en.wikipedia.org/wiki/Wikipedia:Articles_for_deletion'
CURRENT_ID = 'Current_discussions'
OLD_ID = 'Old_discussions'
WP_TAG = re.compile(r'WP:\w+')
BIO_TAGS = frozenset([
    'Authors-related',
    'Businesspeople-related',
    'educators-related',
    'filmmakers-related',
    # 'musicians-related',
    'People-related',
    'Women-related',

    'WP:ANYBIO',
    'WP:ARTIST',
    'WP:BIO',
    'WP:MUSBIO',
    'WP:MUSICBIO',
    'WP:NACTOR',
])


def is_bio(tokens, bio_tags=BIO_TAGS):
    """This returns true if the bag-of-words token set indicates that the entry
    is a biography."""
    return len(tokens & bio_tags) > 0


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


def next_tag(parent, tag, start=0):
    """Find the index of the next tag or None."""
    return child_matching(parent, lambda e: e.tag == tag, start=start)


def all_text(el):
    """Return all text content."""
    text = el.text if el.text is not None else ''
    tail = el.tail if el.tail is not None else ''
    return text + ''.join(all_text(c) for c in el) + tail


def next_h3(parent, start=0):
    """Find the index of the next h3 or None."""
    return next_tag(parent, 'h3', start)


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
    r.encoding = 'latin-1'
    root = etree.fromstring(r.text.strip(), parser)
    with open('get-content.html', 'w') as fout:
        fout.write(r.text.strip())
    return root.find('.//div[@id="mw-content-text"]')


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


def break_by(fn, xs):
    """This breaks xs into chunks. The first item of each chunk passed to fn
    should return True. Other items False.
    """
    accum = collections.deque()

    for x in xs:
        if fn(x) and accum:
            yield list(accum)
            accum.clear()
        accum.append(x)

    if accum:
        yield list(accum)


def get_afds(content):
    """Look through the AfDs on the page and yield (title, tags). """
    for section in break_by(lambda e: e.tag == 'h3', content):
        h3 = section[0]
        title = h3.findtext('./span[@class="mw-headline"]/a')
        if title is None:
            continue

        dli = child_matching(section, lambda e: e.tag == 'dl')
        if dli is not None:
            section = section[dli+1:]

        tags = set()
        tokens = set()
        for el in section:
            text = all_text(el)
            tags |= set(WP_TAG.findall(text))
            tokens |= set(text.split())

        yield (title, tags, tokens)


def main():
    parser = etree.HTMLParser()
    for link in get_afd_index(INDEX_URI, parser):
        print('\n#', link, '\n')
        content = get_content(link, parser)
        for title, tags, tokens in get_afds(content):
            print(title, is_bio(tokens | tags), tags, tokens)


if __name__ == '__main__':
    main()
