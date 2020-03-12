#!/usr/bin/env python3


import csv
import itertools
import operator

import click


def get_year_month(row):
    date = row[0]
    year, month, _ = date.split('-')
    return (year, month)


@click.command()
@click.option('--input', '-i', required=True, type=click.File('r'),
              help='The input file to process.')
@click.option('--output', '-o', required=True,
              help='A template to use for the output filename. {} are replaced '
                   'with the year and month.')
def main(input, output):
    input_rows = csv.reader(input)

    header = next(input_rows)
    input_rows = list(input_rows)

    input_rows.sort(key=operator.itemgetter(0))
    for (key, month_rows) in itertools.groupby(input_rows, key=get_year_month):
        output_filename = output.format(*key)
        with open(output_filename, 'w') as fout:
            writer = csv.writer(fout)
            writer.writerow(header)
            writer.writerows(month_rows)


if __name__ == "__main__":
    main()  #pylint: disable=E1120
