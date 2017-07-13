#!/usr/bin/env python3


import calendar
import collections
import csv
import datetime
from itertools import islice
import re
from urllib.parse import urljoin

import click
from click_datetime import Datetime
from lxml import etree
import requests


INDEX_URI = 'https://en.wikipedia.org/wiki/Wikipedia:Articles_for_deletion'

CURRENT_ID = 'Current_discussions'
OLD_ID = 'Old_discussions'

OUTPUT = 'afd-bios-{}.csv'
HEADER = ('Entry', 'Page Link', 'AfD Link', 'Hits')

WP_TAG = re.compile(r'WP:\w+')
BIO_TAGS = frozenset([
    'Authors-related',
    'Businesspeople-related',
    'educators-related',
    'filmmakers-related',
    # 'musicians-related',
    'People-related',
    'Politicians-related',
    'Sportspeople-related',
    'Women-related',

    'WP:ACADEMIC',
    'WP:ANYBIO',
    'WP:ARTIST',
    'WP:BIO',
    'WP:MUSBIO',
    'WP:MUSICBIO',
    'WP:NACADEMIC',
    'WP:NACTOR',
    'WP:NSPORT',
    'WP:TEACHER',
])


def is_bio(tokens, bio_tags=BIO_TAGS):
    """This returns true if the bag-of-words token set indicates that the entry
    is a biography."""
    return tokens & bio_tags


def is_header(node):
    """Returns True-ish if node is a header (h3 with an a inside)."""
    return ((node.tag == 'h3' and
             node.find('./span[@class="mw-headline"]/a') is not None) or
            (node.tag == 'div' and
             'boilerplate' in node.get('class', '') and
             'xfd-closed' in node.get('class')))


def has_span(id_value, el):
    """Does the element contain span[@id=id_value]?"""
    for span in el.findall('span'):
        if span.get('id') == id_value:
            return True
    return False


def child_matching(el, f, start=0):
    """Return the index of the first child matching f."""
    i = start
    while i < len(el):
        if f(el[i]):
            return i
        i += 1
    return None


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
    """
    Walk all the descendents of a node and return any URLs linked to.

    This also filters out any links whose text are just digits.
    """
    for a in parent.findall('.//a'):
        href = a.get('href')
        if href is not None and not a.text.isdigit():
            yield urljoin(base_uri, href)


def get_content(uri, parser):
    """Retrieves the document at uri and returns #mw-content-text."""
    print('retreiving <{}>'.format(uri))
    r = requests.get(uri)
    root = etree.fromstring(r.content, parser)
    return root.find('.//div[@id="mw-content-text"]/'
                     'div[@class="mw-parser-output"]')


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
    """
    This breaks xs into chunks. The first item of each chunk passed to fn
    should return True. Other items False.
    """
    accum = collections.deque()

    for x in xs:
        if fn(x) and accum:
            yield accum.copy()
            accum.clear()
        accum.append(x)

    if accum:
        yield accum.copy()


def find_text_node(parent, text):
    """
    This returns the first node under parent whose text property == text.
    """
    node = None
    q = collections.deque([parent])

    while len(q) > 0:
        current = q.popleft()
        if current.text == text:
            node = current
            break
        q.extend(list(current))

    return node


def process_text(node, tokens, tags):
    """This gets tags and tokens from node and adds them to the set."""
    text = all_text(node)
    tags |= set(WP_TAG.findall(text))
    tokens |= set(text.split())


def get_afds(content):
    """Look through the AfDs on the page and yield
    (title, link, afd link, tags). """
    count = 0
    for section in break_by(is_header, content):
        if section[0].tag == 'div' and 'xfd-closed' in section[0].get('class'):
            section = collections.deque(section[0])
            while section and section[0].tag != 'h3':
                section.popleft()
            if not section:
                break

        h3 = section.popleft()
        if h3.tag != 'h3':
            continue
        a = h3.find('./span[@class="mw-headline"]/a')
        try:
            title = a.text
        except:
            print(etree.tostring(h3))
            raise
        print('\ttitle: "{}"'.format(title))
        page_link = a.get('href')

        afd_link = None
        tags = set()
        tokens = set()

        while len(section) > 0:
            menu = section.popleft()
            afd_node = find_text_node(menu, 'View AfD')
            if afd_node is None:
                process_text(menu, tokens, tags)
            else:
                afd_link = afd_node.get('href')
                break

        for el in section:
            process_text(el, tokens, tags)

        links = (page_link, afd_link)

        count += 1
        yield (title, links, tags, tokens)
    print('\tyielded {} links'.format(count))


def get_log_page(url, parser):
    """Get a daily log page and return the links from it."""
    content = get_content(url, parser)
    for title, links, tags, tokens in get_afds(content):
        bio_tags = is_bio(tags | tokens)
        if bio_tags:
            yield (
                title,
                urljoin(url, links[0]),
                urljoin(url, links[1]) if links[1] is not None else None,
                ' '.join(sorted(bio_tags)),
                )


def afd_bios(root_url, parser):
    """This yields Entry-Link-Hits tuples for the suspected bios."""
    for link in get_afd_index(root_url, parser):
        yield from get_log_page(link, parser)


def make_day_link(date):
    """Returns a link for the AfD's for a given day."""
    return ('https://en.wikipedia.org/wiki/'
            'Wikipedia:Articles_for_deletion/Log/{}_{}'.format(
                date.strftime('%Y_%B'),
                date.day,
                ))


def iter_first_weeks(start_date, end_date):
    """\
    Iterate over the days in the first week of each month from start_date to
    end_date.

    "Weeks" are the first full week of each month, and weeks begin with Sunday.
    """
    cal = calendar.Calendar(firstweekday=6)
    current = start_date.replace(day=1)
    while current <= end_date:
        month = cal.itermonthdates(current.year, current.month)

        first_week = list(islice(month, 7))
        if first_week[0].day > 7:
            first_week = islice(month, 7)

        yield from first_week

        if current.month == 12:
            current = current.replace(year=current.year+1, month=1)
        else:
            current = current.replace(month=current.month+1)


def afd_weeklies(start_date, end_date, parser):
    """Generate weekly AfDs for the first week of each month."""
    for day in iter_first_weeks(start_date, end_date):
        url = make_day_link(day)
        yield from get_log_page(url, parser)


@click.command()
@click.option('--date', '-d', default=None, type=Datetime(format='%Y-%m-%d'),
              help="The date to get the AfD's for. Defaults to everything "
                   "listed on the main AfD page. The format is YYYY-MM-DD.")
@click.option('--weekly', default=False, is_flag=True,
              help='Generate reports for the first week of each month, '
                   'starting with DATE and continuing to now.')
@click.option('--output', '-o', default=None,
              help='The output file. It defaults to afd-bios-DATE.csv.')
def main(date, weekly, output):
    """Download AfDs for a date or range."""
    full_afd = False
    if date is None:
        full_afd = True
        date = datetime.date.today()
    else:
        date = date.date()

    if output is None:
        output = OUTPUT.format(date.strftime('%Y%m%d'))

    parser = etree.HTMLParser()
    with open(output, 'w') as fout:
        writer = csv.writer(fout)
        writer.writerow(HEADER)

        if full_afd:
            writer.writerows(afd_bios(INDEX_URI, parser))
        elif weekly:
            writer.writerows(afd_weeklies(date, datetime.date.today(),
                                          parser))
        else:
            url = make_day_link(date)
            writer.writerows(get_log_page(url, parser))


if __name__ == '__main__':
    main()
