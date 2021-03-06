#!/usr/bin/env python3


import calendar
import collections
import csv
import datetime
from itertools import islice
import logging
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
HEADER = ('AfD Date', 'Entry', 'Page Link', 'AfD Link', 'Hits', 'Keep')

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


def critical(*args, **kwargs):
    logging.getLogger('afd').critical(*args, **kwargs)


def error(*args, **kwargs):
    logging.getLogger('afd').error(*args, **kwargs)


def warning(*args, **kwargs):
    logging.getLogger('afd').warning(*args, **kwargs)


def info(*args, **kwargs):
    logging.getLogger('afd').info(*args, **kwargs)


def debug(*args, **kwargs):
    logging.getLogger('afd').info(*args, **kwargs)


def exception(*args, **kwargs):
    logging.getLogger('afd').exception(*args, **kwargs)


def get_content(uri, parser, links=False):
    """\
    Retrieves the document at uri and returns #mw-content-text.

    Optionally, it also returns the link elements as a dict.
    """
    info('retreiving <{}>'.format(uri))
    r = requests.get(uri)
    root = etree.fromstring(r.content, parser)
    content = root.find('.//div[@id="mw-content-text"]/'
                        'div[@class="mw-parser-output"]')

    if links:
        link_dict = {
            link.get('rel'): link.get('href')
            for link in root.iter('link')
            }
        retval = (link_dict, content)
    else:
        retval = content

    return retval


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


def get_afds(afd_date, content):
    """Look through the AfDs on the page and yield
    (date_of_afd, title, link, afd link, tags, keep_flag). """
    afd_date = afd_date.strftime('%Y-%m-%d')
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
        span = h3.find('.//span[@class="mw-headline"]')
        try:
            if len(span) == 0:
                title = span.text
                page_link = None
                keep = False
            else:
                a = span[0]
                title = a.text
                page_link = a.get('href')
                keep = a.get('class', None) != 'new'
        except:
            exception(etree.tostring(h3))
            raise
        debug('title: "%s"', title)

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
        yield (afd_date, title, links, tags, tokens, keep)
    info('yielded %d links', count)


def url_to_date(url):
    """This parses a URL, taking the last part and parsing it to a datetime."""
    parts = url.split('/')
    date_path = parts.pop()
    return datetime.datetime.strptime(date_path, '%Y_%B_%d')


def get_log_page(url, parser):
    """Get a daily log page and return the links from it."""
    links, content = get_content(url, parser, links=True)
    page_date = url_to_date(links['canonical'])
    for date, title, links, tags, tokens, keep in get_afds(page_date, content):
        bio_tags = is_bio(tags | tokens)
        if bio_tags:
            yield (
                date,
                title,
                urljoin(url, links[0]),
                urljoin(url, links[1]) if links[1] is not None else None,
                ' '.join(sorted(bio_tags)),
                keep,
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


def in_week(cal, cache, week_num, date):
    """\
    Returns True if date is in week # week_num.

    The calculations are based off of the calendar passed in, and work
    that might apply to this calculation on other dates are stored in the
    cache.

    >>> cal = calendar.Calendar()
    >>> cache = {}
    >>> jul1 = datetime.date(2017, 7, 1)
    >>> [in_week(cal, cache, week, jul1) for week in range(6)]
    [True, False, False, False, False, False]
    >>> jul4 = datetime.date(2017, 7, 4)
    >>> [in_week(cal, cache, week, jul4) for week in range(6)]
    [False, True, False, False, False, False]
    >>> jul12 = datetime.date(2017, 7, 12)
    >>> [in_week(cal, cache, week, jul12) for week in range(6)]
    [False, False, True, False, False, False]
    >>> jul20 = datetime.date(2017, 7, 20)
    >>> [in_week(cal, cache, week, jul20) for week in range(6)]
    [False, False, False, True, False, False]
    >>> jul28 = datetime.date(2017, 7, 28)
    >>> [in_week(cal, cache, week, jul28) for week in range(6)]
    [False, False, False, False, True, False]
    >>> jul31 = datetime.date(2017, 7, 31)
    >>> [in_week(cal, cache, week, jul31) for week in range(6)]
    [False, False, False, False, False, True]
    """
    key = (date.year, date.month, week_num)

    if key not in cache:
        month = cal.itermonthdates(date.year, date.month)

        current_week = list(islice(month, 7))
        if week_num > 0 and current_week[0].day <= 7:
            week_num -= 1
        for _ in range(week_num):
            current_week = list(islice(month, 7))

        cache[key] = set(current_week)

    return date in cache[key]


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


class DateRange(click.ParamType):
    name = 'date-range'

    def convert(self, value, param, ctx):
        start, end = value.split('/')
        return (datetime.datetime.strptime(start, '%Y-%m-%d'),
                datetime.datetime.strptime(end, '%Y-%m-%d'))


@click.command()
@click.option('--date', '-d', default=None, type=Datetime(format='%Y-%m-%d'),
              help="The date to get the AfD's for. Defaults to everything "
                   "listed on the main AfD page. The format is YYYY-MM-DD.")
@click.option('--date-range', '-r', default=None, type=DateRange(),
              help="An inclusive range of dates to scrape. The format is "
                   "YYYY-MM-DD/YYYY-MM-DD")
@click.option('--week', '-w', default=None, type=int,
              help='Generate reports only for a particular week '
                   'of the month. 0 is the first week, 1 is the '
                   'first full week of the month. Omitting this '
                   'processes all days. This only applies in '
                   'conjunction with either --date or --date-range.')
@click.option('--level', '-l', default='WARNING',
              type=click.Choice(['CRITICAL', 'ERROR', 'WARNING', 'INFO',
                                 'DEBUG']))
@click.option('--output', '-o', default=None,
              help='The output file. It defaults to afd-bios-DATE.csv.')
@click.option('--test', '-t', is_flag=True,
              help='Run doctests on the functions instead of scraping '
                   'Wikipedia.')
def main(date, date_range, week, level, output, test):
    """Download AfDs for a date or range."""
    logging.basicConfig()
    logging.getLogger('afd').setLevel(getattr(logging, level))

    if test:
        import doctest
        failure_count, test_count = doctest.testmod()
        raise SystemExit(failure_count)

    parser = etree.HTMLParser()
    day = datetime.timedelta(days=1)

    if date and date_range is None:
        date_range = (date, date + day)

    if date_range:
        current, end = date_range
        date = current
        dates = []
        while current < end:
            dates.append(current.date())
            current += day

        if week:
            cal = calendar.Calendar(firstweekday=6)
            week_cache = {}
            dates = (date for date in dates
                     if in_week(cal, week_cache, week, date))

        links = (make_day_link(date) for date in dates)

    else:
        links = get_afd_index(INDEX_URI, parser)

    if output is None:
        output = OUTPUT.format(date.strftime('%Y%m%d'))

    with open(output, 'w') as fout:
        writer = csv.writer(fout)
        writer.writerow(HEADER)
        for link in links:
            writer.writerows(get_log_page(link, parser))


if __name__ == '__main__':
    main()
