#!/usr/bin/env python3


from collections import namedtuple
import csv
import datetime
from itertools import dropwhile, takewhile
from urllib.parse import urljoin

import click
from click_datetime import Datetime
from lxml import etree
import requests

from afd import get_content


HEADER = ('title', 'user', 'timestamp', 'url', 'original', 'history')
NewPageInfo = namedtuple('NewPageInfo', HEADER)

DATE = datetime.date(2017, 3, 11)


def iter_new_pages(url, content):
    """This iterates over all the new pages listed in content."""
    for i, ul in enumerate(content.findall('.//ul')):
        if i == 0:
            continue
        for li in ul.findall('li'):
            try:
                a_tag = li.find('a')
                title = a_tag.get('title')
                original = urljoin(url, a_tag.get('href'))

                time = datetime.datetime.strptime(
                    li.find('.//span[@class="mw-newpages-time"]').text,
                    '%H:%M, %d %B %Y',
                    )

                a_tag = li.find('a[@class="mw-newpages-pagename"]')
                page_url = urljoin(url, a_tag.get('href'))

                user = None
                for a_tag in li.findall('.//a'):
                    class_set = set(a_tag.get('class', '').split())
                    if 'mw-userlink' in class_set:
                        user = a_tag.text
                        break
                else:
                    raise "Missing user."

                history = urljoin(
                    url,
                    li.find('span[@class="mw-newpages-history"]/a').get('href')
                    )

            except:
                print('ERROR ON')
                print(etree.tostring(li))
                raise

            print(title, time, time.date(), DATE, time.date() < DATE, time.date() == DATE)
            yield NewPageInfo(title, user, time, page_url, original,
                                  history)


def get_next(url, content):
    """This returns the link to the next page in content."""
    a_tag = content.find('.//a[@class="mw-nextlink"]')
    if a_tag is not None:
        href = a_tag.get('href')
        return urljoin(url, href)
    else:
        return None


def make_day_link(date):
    """\
    Return the new page log link for date.

    Actually, this started looking backward from midnight the
    following day.
    """
    day = datetime.timedelta(days=1)
    next_day = date + day
    return ('https://en.wikipedia.org/w/index.php?'
            'title=Special:NewPages&'
            'offset={}000000&'
            'limit=500'.format(
                next_day.strftime('%Y%m%d')))

                
def get_new(url, parser):
    """\
    While the page is for the given date, download the new pages
    starting from url.
    """
    content = get_content(url, parser)
    yield from iter_new_pages(url, content)
    next_page = get_next(url, content)
    if next_page is not None:
        yield from get_new(next_page, parser)
    


@click.command()
@click.option('--date', '-d', default=None,
              type=Datetime(format='%Y-%m-%d'),
              help='The date to get new articles for. The format '
                   'is YYYY-MM-DD. Defaults to today.')
@click.option('--output', '-o', default=None,
              help='The output file. It default to new-DATE.csv.')
def main(date, output):
    """Scrapes links to all new pages generated on a date."""
    if date is None:
        date = datetime.date.today()
    else:
        date = date.date()

    if output is None:
        output = 'new-{}.csv'.format(date.strftime('%Y%m%d'))

    parser = etree.HTMLParser()
    with open(output, 'w') as fout:
        writer = csv.writer(fout)
        writer.writerow(NewPageInfo._fields)

        url = make_day_link(date)
        rows = get_new(url, parser)
        rows = dropwhile(lambda r: r.timestamp.date() < date, rows)
        rows = takewhile(lambda r: r.timestamp.date() == date, rows)
        writer.writerows(rows)
        
        
if __name__ == '__main__':
    main()
